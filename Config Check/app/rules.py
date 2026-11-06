"""Deterministic rule engine: template blocks, built-in checks and role drift."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .common import KNOWLEDGE, Device, Finding, inventory

CATEGORY = {"base": "Base", "infra": "Infra", "services": "Service"}
VALUE = r'(?:"[^"]*"|\S+)'
PH = re.compile(r"(\{\{\s*[^}]+?\s*\}\})")
META = re.compile(r'@(\w+)\s+(?:"([^"]*)"|(\S+))')


@dataclass
class Block:
    id: str
    sev: int
    title: str
    doc: str
    category: str
    source_file: str
    scope: str | None = None
    builtin: str | None = None
    required: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    practice: str = ""           # best-practice text shown on the dashboard (@practice)

    def text(self) -> str:
        """Human/LLM-readable form of the block (used for retrieval)."""
        out = [f"Template {self.source_file} rule {self.id} (severity {self.sev}): {self.title}. Ref {self.doc}."]
        if self.scope:
            out.append(f"Applies once per match of: {self.scope}")
        if self.builtin:
            out.append(f"Built-in check: {self.builtin}")
        out += [f"Required: {l}" for l in self.required]
        out += [f"Forbidden: {l}" for l in self.forbidden]
        out += self.comments
        return "\n".join(out)


# ---------------------------------------------------------------- templates

def template_files(selectors: list[str]) -> list[Path]:
    base = KNOWLEDGE / "templates"
    files: list[Path] = []
    for sel in selectors or []:
        p = base / sel
        if p.is_dir():
            files += sorted(p.rglob("*.set"))
        elif p.with_suffix(".set").is_file():
            files.append(p.with_suffix(".set"))
    return list(dict.fromkeys(files))


def parse_template(path: Path) -> list[Block]:
    rel = path.relative_to(KNOWLEDGE / "templates")
    category = CATEGORY.get(rel.parts[0], rel.parts[0].title())
    blocks: list[Block] = []
    cur: Block | None = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# @scope "):
            if cur:
                cur.scope = line[len("# @scope "):].strip()
        elif line.startswith("# @practice "):
            if cur:
                m = re.match(r'# @practice\s+"?(.*?)"?\s*$', line)
                cur.practice = m.group(1) if m else ""
        elif line.startswith("# @builtin "):
            if cur:
                cur.builtin = line.split(None, 2)[2].strip()
        elif line.startswith("# @") and "@id" in line:
            meta = {m.group(1): m.group(2) if m.group(2) is not None else m.group(3) for m in META.finditer(line)}
            cur = Block(id=meta["id"], sev=int(meta.get("sev", 3)), title=meta.get("title", meta["id"]),
                        doc=meta.get("doc", ""), category=category, source_file=str(rel.with_suffix("")))
            blocks.append(cur)
        elif line.startswith("#"):
            if cur:
                cur.comments.append(line.lstrip("# "))
        elif line.startswith("!set ") and cur:
            cur.forbidden.append(line[1:])
        elif line.startswith("set ") and cur:
            cur.required.append(line)
    return blocks


def load_blocks(selectors: list[str]) -> list[Block]:
    return [b for f in template_files(selectors) for b in parse_template(f)]


def _compile(tmpl: str, binds: dict) -> re.Pattern:
    out = []
    for part in PH.split(tmpl):
        if PH.fullmatch(part):
            name = part.strip("{} ")
            if name == "*":
                out.append(".*")
            elif name in binds:
                out.append(re.escape(str(binds[name])))
            else:
                out.append(VALUE)
        else:
            out.append(re.escape(part))
    return re.compile("^" + "".join(out) + "$")


def _fill(tmpl: str, binds: dict) -> str:
    def rep(m):
        name = m.group(1).strip("{} ")
        if name == "*":
            return "<value>"
        return str(binds.get(name, f"<{name}>"))
    return PH.sub(rep, tmpl).replace("{{*}}", "<value>")


def _common_path(lines: list[str]) -> str:
    toks = [l.split()[1:] for l in lines]
    common = []
    for parts in zip(*toks):
        if len(set(parts)) != 1:
            break
        common.append(parts[0])
    if len(lines) == 1:
        common = common[:4]
    elif not common and toks:
        common = toks[0][:2]
    return " ".join(t for t in common[:6] if "<" not in t)


def _conflicts(lines: list[str], filled: str) -> list[str]:
    """Same statement with a different value: everything but the last token matches."""
    toks = filled.split()
    if len(toks) < 4:
        return []
    stem = " ".join(toks[:-1]) + " "
    return [l for l in lines if l.startswith(stem) and l != filled][:4]


def _siblings(lines: list[str], filled: str) -> list[str]:
    """Neighbouring config under the same parent, shown for context only."""
    toks = filled.split()
    if len(toks) < 6:
        return []
    stem = " ".join(toks[:-2]) + " "
    return [l for l in lines if l.startswith(stem)][:3]


# ---------------------------------------------------------------- evaluation

def evaluate_block(b: Block, lines: list[str], dev: Device) -> list[Finding]:
    if b.builtin:
        fn = BUILTINS.get(b.builtin)
        return fn(b, lines, dev) if fn else []

    if b.scope:
        rx = re.compile(b.scope)
        insts, seen = [], set()
        for l in lines:
            m = rx.search(l)
            if m:
                key = tuple(sorted(m.groupdict().items()))
                if key not in seen:
                    seen.add(key)
                    insts.append(m.groupdict())
        if not insts:
            return []
    else:
        insts = [{}]

    # One finding per block per device; scope instances are grouped inside it.
    ev: list[str] = []
    fix: list[str] = []
    affected: list[str] = []
    conflict = False
    n_missing = 0
    forbidden_hits: list[str] = []
    for inst in insts:
        binds = {**dev.vars, **inst}
        where = ", ".join(str(v) for v in inst.values())
        missing = [t for t in b.required if not any(_compile(t, binds).match(l) for l in lines)]
        if missing:
            affected.append(where)
            n_missing += len(missing)
            filled = [_fill(t, binds) for t in missing]
            ctx: list[str] = []
            for f in filled:
                for c in _conflicts(lines, f):
                    conflict = True
                    ctx.append(f"CONFLICT: {c}")
                if not ctx:
                    ctx += _siblings(lines, f)
            for e in ctx + [f"MISSING: {f}" for f in filled]:
                if e not in ev:
                    ev.append(e)
            fix += [f for f in filled if f not in fix]
        for t in b.forbidden:
            rx = _compile(t, binds)
            for h in lines:
                if rx.match(h) and h not in forbidden_hits:
                    forbidden_hits.append(h)

    out: list[Finding] = []
    if n_missing:
        scope_txt = ""
        if b.scope and any(affected):
            scope_txt = f" Affects {len(affected)} instance{'s' if len(affected) > 1 else ''}: {', '.join(affected)}."
        reason = (f"{n_missing} line{'s' if n_missing > 1 else ''} required by template "
                  f"{b.source_file} ({b.id}) {'is' if n_missing == 1 else 'are'} missing.{scope_txt}")
        if conflict:
            reason += " The device has a different value configured."
        title = b.title + (f" ({len(affected)} instances)" if len(affected) > 1 else "")
        masked = fix
        if len(affected) > 1:
            vals = {str(v) for i in insts for v in i.values()}
            masked = [" ".join("*" if t in vals else t for t in f.split()) for f in fix]
        out.append(Finding(device=dev.name, role=dev.role, category=b.category, source="Rule",
                           severity=b.sev, title=title, path=_common_path(masked),
                           reason=reason, evidence=ev[:24], fix=fix, doc=b.doc, rule_id=b.id))
    if forbidden_hits:
        out.append(Finding(device=dev.name, role=dev.role, category=b.category, source="Rule",
                           severity=b.sev, title=b.title, path=_common_path(forbidden_hits),
                           reason=f"Template {b.source_file} ({b.id}) forbids this configuration.",
                           evidence=[f"CONFLICT: {h}" for h in forbidden_hits],
                           fix=["delete " + h[4:] for h in forbidden_hits], doc=b.doc,
                           rule_id=b.id + "!"))
    return out


# ---------------------------------------------------------------- built-ins

def builtin_vlan_name_tags(b: Block, lines: list[str], dev: Device) -> list[Finding]:
    out = []
    vlans: dict[str, list[str]] = defaultdict(list)
    for l in lines:
        m = re.match(r"^set vlans (\S+) ", l)
        if m:
            vlans[m.group(1)].append(l)
    for name, vl in vlans.items():
        nm = re.fullmatch(r"QINQ-(\d+)-(\d+)", name)
        if not nm:
            continue
        s_name, c_name = nm.groups()
        for l in vl:
            mi = re.match(rf"^set vlans {re.escape(name)} interface (\S+)\.(\d+)$", l)
            if not mi:
                continue
            ifd, unit = mi.groups()
            tag_lines = [x for x in lines if x.startswith(f"set interfaces {ifd} unit {unit} vlan-tags ")]
            outer = next((x.split()[-1] for x in tag_lines if " outer " in x), None)
            inner = next((x.split()[-1] for x in tag_lines if " inner " in x), None)
            if outer and inner and (outer, inner) != (s_name, c_name):
                good = f"QINQ-{outer}-{inner}"
                out.append(Finding(
                    device=dev.name, role=dev.role, category=b.category, source="Rule", severity=b.sev,
                    title=b.title, path=f"vlans {name}",
                    reason=(f"VLAN {name} implies outer {s_name} / inner {c_name}, but its member "
                            f"{ifd}.{unit} is tagged outer {outer} / inner {inner}. "
                            f"Expected name {good}."),
                    evidence=[f"CONFLICT: set vlans {name} interface {ifd}.{unit}"] + tag_lines,
                    fix=[f"rename vlans {name} to {good}"], doc=b.doc, rule_id=f"{b.id}@vlan={name}"))
    return out


def builtin_orphan_mclag(b: Block, lines: list[str], dev: Device) -> list[Finding]:
    mc = [l for l in lines if l.startswith("set multi-chassis ")]
    if mc and not any(" mc-ae " in l for l in lines):
        return [Finding(device=dev.name, role=dev.role, category=b.category, source="Rule", severity=b.sev,
                        title=b.title, path="multi-chassis",
                        reason="multi-chassis configuration is present but no interface uses mc-ae.",
                        evidence=[f"CONFLICT: {l}" for l in mc], fix=["delete multi-chassis"],
                        doc=b.doc, rule_id=b.id)]
    return []


def _f(b: Block, dev: Device, sev: int, title: str, path: str, reason: str,
       evidence: list[str], fix: list[str], rid: str) -> Finding:
    return Finding(device=dev.name, role=dev.role, category=b.category, source="Rule", severity=sev,
                   title=title, path=path, reason=reason, evidence=evidence[:24], fix=fix,
                   doc=b.doc, rule_id=rid)


def builtin_fabric_peers(b: Block, lines: list[str], dev: Device) -> list[Finding]:
    """Underlay and overlay BGP sessions against the inventory.

    The device's role sets vars.peer_role (spines peer with leaves and vice versa).
    Each peer device needs vars.lo0 and vars.asn.
    """
    peer_role = dev.vars.get("peer_role")
    if not peer_role:
        return []
    _, devs = inventory()
    peers = [d for d in devs if d.role == peer_role and d.vars.get("lo0") and d.vars.get("asn")]
    if not peers:
        return []
    known_lo = {str(d.vars["lo0"]): d for d in devs if d.vars.get("lo0")}
    peer_asn = {str(d.vars["asn"]): d for d in peers}

    def sessions(group: str) -> dict[str, str]:
        rx = re.compile(rf"^set protocols bgp group {group} neighbor (\S+) peer-as (\S+)$")
        return {m.group(1): m.group(2) for l in lines if (m := rx.match(l))}

    out: list[Finding] = []
    ol, ul = sessions("OVERLAY"), sessions("UNDERLAY")

    # Overlay: one session per peer loopback, peer-as = that peer's ASN.
    ev, fix, miss = [], [], []
    for p in peers:
        lo, asn = str(p.vars["lo0"]), str(p.vars["asn"])
        want = f"set protocols bgp group OVERLAY neighbor {lo} peer-as {asn}"
        if ol.get(lo) == asn:
            continue
        miss.append(p.name)
        if lo in ol:
            ev.append(f"CONFLICT: set protocols bgp group OVERLAY neighbor {lo} peer-as {ol[lo]}")
        ev.append(f"MISSING: {want}")
        fix += [want, f"set protocols bgp group OVERLAY neighbor {lo} description {p.name.upper()}"]
    if miss:
        out.append(_f(b, dev, b.sev, "Overlay session missing or wrong peer-as to " + ", ".join(miss),
                      "protocols bgp group OVERLAY",
                      f"Inventory role {dev.role} must peer in OVERLAY with every {peer_role} loopback. "
                      f"{len(miss)} of {len(peers)} are missing or have the wrong peer-as.",
                      ev, fix, f"{b.id}@overlay"))

    # Overlay: neighbors that are not peer-role devices.
    stray = [n for n in ol if n not in {str(p.vars["lo0"]) for p in peers}]
    if stray:
        who = [f"{n} ({known_lo[n].name}, role {known_lo[n].role})" if n in known_lo else f"{n} (not in inventory)"
               for n in stray]
        out.append(_f(b, dev, 3, "Unexpected overlay neighbor", "protocols bgp group OVERLAY",
                      f"OVERLAY neighbors must be {peer_role} loopbacks only. Unexpected: {', '.join(who)}.",
                      [l for l in lines if any(f" OVERLAY neighbor {n} " in l for n in stray)],
                      [f"delete protocols bgp group OVERLAY neighbor {n}" for n in stray], f"{b.id}@overlay-stray"))

    # Underlay: at least one session per peer ASN, and no unknown ASNs.
    have = set(ul.values())
    miss_ul = [p for p in peers if str(p.vars["asn"]) not in have]
    if miss_ul:
        out.append(_f(b, dev, b.sev, "Underlay session missing to " + ", ".join(p.name for p in miss_ul),
                      "protocols bgp group UNDERLAY",
                      f"Every {dev.role} needs an UNDERLAY session to every {peer_role}. No session with "
                      f"peer-as {', '.join(str(p.vars['asn']) for p in miss_ul)} was found. "
                      "A missing session removes a fabric path.",
                      [l for l in lines if " group UNDERLAY neighbor " in l and " peer-as " in l]
                      + [f"MISSING: set protocols bgp group UNDERLAY neighbor <link address> peer-as {p.vars['asn']}"
                         for p in miss_ul],
                      [], f"{b.id}@underlay"))
    bad = {n: a for n, a in ul.items() if a not in peer_asn}
    if bad:
        out.append(_f(b, dev, 3, "Underlay neighbor with an ASN that is not a fabric peer",
                      "protocols bgp group UNDERLAY",
                      f"UNDERLAY peer-as must be the ASN of a {peer_role} in the inventory "
                      f"({', '.join(sorted(peer_asn))}).",
                      [f"CONFLICT: set protocols bgp group UNDERLAY neighbor {n} peer-as {a}" for n, a in bad.items()],
                      [], f"{b.id}@underlay-asn"))
    return out


def builtin_vni_mapping(b: Block, lines: list[str], dev: Device) -> list[Finding]:
    """VLAN V<id> carries VNI vni_base + id. The factory 'default' VLAN is ignored."""
    base = int(dev.vars.get("vni_base", 10000))
    prefix = str(dev.vars.get("vlan_prefix", "V"))
    ids, vnis = {}, {}
    for l in lines:
        if m := re.match(r"^set vlans (\S+) vlan-id (\d+)$", l):
            ids[m.group(1)] = int(m.group(2))
        elif m := re.match(r"^set vlans (\S+) vxlan vni (\d+)$", l):
            vnis[m.group(1)] = int(m.group(2))
    out: list[Finding] = []
    ev, fix, names = [], [], []
    for name, vid in ids.items():
        if name == "default":
            continue
        want = base + vid
        got = vnis.get(name)
        if got != want:
            names.append(name)
            if got is not None:
                ev.append(f"CONFLICT: set vlans {name} vxlan vni {got}")
            ev += [f"set vlans {name} vlan-id {vid}", f"MISSING: set vlans {name} vxlan vni {want}"]
            fix.append(f"set vlans {name} vxlan vni {want}")
    if names:
        out.append(_f(b, dev, b.sev, b.title + f" ({', '.join(names)})", "vlans",
                      f"VNI must be {base} + VLAN ID so every leaf maps the VLAN to the same VNI. "
                      f"{len(names)} VLAN{'s' if len(names) > 1 else ''} wrong or not stretched.",
                      ev, fix, b.id))
    badname = [(n, v) for n, v in ids.items() if n != "default" and n != f"{prefix}{v}"]
    if badname:
        out.append(_f(b, dev, 2, "VLAN name does not follow V<vlan-id>", "vlans",
                      "Stretched VLANs are named " + prefix + "<vlan-id> so names match on every leaf.",
                      [f"CONFLICT: set vlans {n} vlan-id {v}" for n, v in badname],
                      [f"rename vlans {n} to {prefix}{v}" for n, v in badname], b.id + "@name"))
    return out


def builtin_bgp_auth(b: Block, lines: list[str], dev: Device) -> list[Finding]:
    """Every BGP group must be authenticated at group level, or on every one of its neighbors."""
    groups: dict[str, set] = {}
    for l in lines:
        if m := re.match(r"^set protocols bgp group (\S+) neighbor (\S+)", l):
            groups.setdefault(m.group(1), set()).add(m.group(2))
        elif m := re.match(r"^set protocols bgp group (\S+) ", l):
            groups.setdefault(m.group(1), set())
    auth = re.compile(r" authentication-(key|key-chain) ")
    bad = []
    for g, nbrs in groups.items():
        if any(l.startswith(f"set protocols bgp group {g} ") and auth.search(l) and " neighbor " not in l for l in lines):
            continue
        unauth = [n for n in sorted(nbrs) if not any(
            l.startswith(f"set protocols bgp group {g} neighbor {n} ") and auth.search(l) for l in lines)]
        if unauth or not nbrs:
            bad.append((g, unauth))
    if not bad:
        return []
    n = sum(len(u) for _, u in bad)
    ev = [f"MISSING: set protocols bgp group {g} authentication-key <key>" for g, _ in bad]
    ev += [l for l in lines if any(l.startswith(f"set protocols bgp group {g} neighbor {x} peer-as") for g, u in bad for x in u)]
    return [Finding(device=dev.name, role=dev.role, category=b.category, source="Rule", severity=b.sev,
                    title=f"{b.title} ({n} session{'s' if n != 1 else ''} in {', '.join(g for g, _ in bad)})",
                    path="protocols bgp", reason=f"{n} BGP session{'s are' if n != 1 else ' is'} not authenticated. "
                    "Without authentication a session can be spoofed or reset by anyone who can reach the peering address.",
                    evidence=ev[:24], fix=[f"set protocols bgp group {g} authentication-key \"<shared key>\"" for g, _ in bad],
                    doc=b.doc, rule_id=b.id, practice=b.practice)]


BUILTINS = {"bgp_auth": builtin_bgp_auth,
            "vlan_name_tags": builtin_vlan_name_tags, "orphan_mclag": builtin_orphan_mclag,
            "fabric_peers": builtin_fabric_peers, "vni_mapping": builtin_vni_mapping}


# ---------------------------------------------------------------- drift

def _group(line: str) -> str:
    t = line.split()
    return " ".join(t[1:3]) if len(t) > 2 else " ".join(t[1:])


def role_drift(role: str, configs: dict[str, list[str]], ignore: list[str],
               devices: dict[str, Device]) -> list[Finding]:
    if len(configs) < 2:
        return []
    ign = [re.compile(p) for p in ignore or []]
    keep = {d: {l for l in ls if not any(r.search(l) for r in ign)} for d, ls in configs.items()}
    out = []
    for dev, mine in keep.items():
        others = [s for d, s in keep.items() if d != dev]
        only_here = sorted(l for l in mine if not any(l in o for o in others))
        by_group: dict[str, list[str]] = defaultdict(list)
        for l in only_here:
            by_group[_group(l)].append(l)
        peers = ", ".join(d for d in keep if d != dev)
        for grp, ls in by_group.items():
            out.append(Finding(
                device=dev, role=role, category="Drift", source="Rule", severity=2,
                title=f"Differs from role peers: {grp}", path=grp,
                reason=(f"{len(ls)} line{'s' if len(ls) > 1 else ''} under '{grp}' exist on {dev} "
                        f"but not on {peers}. Devices in role {role} should match apart from "
                        f"per-device values."),
                evidence=ls[:12], fix=[], doc=f"inventory role {role}", rule_id=f"DRIFT@{grp}"))
    return out


def run_rules(dev: Device, lines: list[str], blocks: list[Block]) -> list[Finding]:
    out: list[Finding] = []
    for b in blocks:
        fs = evaluate_block(b, lines, dev)
        for f in fs:
            f.practice = f.practice or b.practice
        out += fs
    return out
