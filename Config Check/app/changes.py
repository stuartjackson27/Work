"""Config history: commit parsing, snapshot diffs and change risk hints."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone

# Lines that change on their own and are not interesting as config changes.
DIFF_IGNORE = [r"^set version "]

COMMIT_RX = re.compile(
    r"^\s*(\d+)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\S+) by (\S+) via (\S+)(.*)$")

# Deterministic risk hints for added (+) or removed (-) lines. (pattern, side, risk, reason)
RISK_HINTS = [
    (r"^set system services (telnet|ftp)\b", "+", 4, "Clear-text management service enabled"),
    (r"^set system services ssh root-login allow", "+", 4, "Root SSH login enabled"),
    (r"^set snmp community ", "+", 4, "SNMPv2c community added"),
    (r"^set system root-authentication ", "+", 3, "Root password changed"),
    (r"^set system login user ", "+", 3, "Local user account added or changed"),
    (r"^set system login user ", "-", 2, "Local user account removed"),
    (r"^set (routing-instances \S+ )?protocols bgp .*(authentication-key|import|export)", "-", 4,
     "BGP authentication or policy removed"),
    (r"^set (routing-instances \S+ )?protocols bgp ", "-", 3, "BGP configuration removed"),
    (r"^set (routing-instances \S+ )?protocols bgp .* neighbor ", "+", 3, "BGP neighbor added"),
    (r"^set (routing-instances \S+ )?protocols bgp .* peer-as ", "+", 3, "BGP peer AS changed"),
    (r"^set firewall ", "-", 3, "Firewall filter configuration removed"),
    (r"^set vlans \S+ vxlan vni ", "+", 4, "VXLAN VNI mapping changed"),
    (r"^set vlans \S+ vxlan vni ", "-", 4, "VLAN removed from VXLAN"),
    (r"^set switch-options (vrf-target|route-distinguisher|vtep-source-interface) ", "+", 4,
     "EVPN route target, RD or VTEP source changed"),
    (r"^set protocols evpn ", "-", 4, "EVPN configuration removed"),
    (r"^set protocols bgp group OVERLAY keep all", "-", 5, "Spine keep all removed (EVPN routes dropped)"),
    (r"^set routing-options (router-id|autonomous-system) ", "+", 3, "Router-id or ASN changed"),
    (r"^set interfaces \S+ (unit \d+ )?vlan-tags ", "+", 3, "QinQ tags changed"),
    (r"^set interfaces \S+ (unit \d+ )?family inet address ", "+", 2, "Interface address changed"),
    (r"^set interfaces \S+ mtu ", "+", 2, "Interface MTU changed"),
    (r"^set protocols lldp ", "-", 2, "LLDP removed"),
    (r"^set system (ntp|syslog) ", "-", 2, "Time or logging configuration removed"),
    (r"^deactivate ", "+", 3, "Configuration deactivated"),
]


def parse_commits(text: str) -> list[dict]:
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = COMMIT_RX.match(line)
        if not m:
            continue
        n, ts, tz, user, via, rest = m.groups()
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            iso = dt.isoformat(timespec="seconds")
        except ValueError:
            iso = ts
        comment = ""
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if nxt.startswith("    ") and not COMMIT_RX.match(nxt):
            comment = nxt.strip()
        out.append({"rollback": int(n), "time": iso, "user": user, "via": via,
                    "note": rest.strip(), "comment": comment})
    return out


def commits_between(commits: list[dict], after_iso: str | None, until_iso: str | None) -> list[dict]:
    res = []
    for c in commits:
        t = c.get("time", "")
        if after_iso and t <= after_iso:
            continue
        if until_iso and t > until_iso:
            continue
        res.append(c)
    return res


def _section(line: str) -> str:
    t = line.split()
    if len(t) > 3 and t[1] in ("routing-instances", "interfaces", "vlans", "policy-options"):
        return " ".join(t[1:3])
    return " ".join(t[1:3]) if len(t) > 2 else " ".join(t[1:])


def diff_configs(old: list[str], new: list[str]) -> dict:
    ign = [re.compile(p) for p in DIFF_IGNORE]
    o = {l for l in old if not any(r.search(l) for r in ign)}
    n = {l for l in new if not any(r.search(l) for r in ign)}
    added, removed = sorted(n - o), sorted(o - n)
    sections: dict[str, dict] = defaultdict(lambda: {"added": [], "removed": []})
    for l in added:
        sections[_section(l)]["added"].append(l)
    for l in removed:
        sections[_section(l)]["removed"].append(l)
    return {"added": added, "removed": removed, "sections": dict(sections)}


def risk_hints(added: list[str], removed: list[str]) -> list[dict]:
    hints, seen = [], set()
    for rx, side, risk, reason in RISK_HINTS:
        pool = added if side == "+" else removed
        hits = [l for l in pool if re.search(rx, l)]
        if hits and reason not in seen:
            seen.add(reason)
            hints.append({"risk": risk, "reason": reason, "lines": [("+ " if side == "+" else "- ") + h for h in hits[:6]]})
    return sorted(hints, key=lambda h: -h["risk"])
