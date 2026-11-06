"""Ollama client and the LLM configuration assessor."""
from __future__ import annotations

import copy
import json
import re
import time
from collections import defaultdict

import httpx

from .common import Device, Finding, inventory
from .knowledge import Retriever
from .rules import PH, VALUE, load_blocks

# ------------------------------------------------------------------ client


class Ollama:
    def __init__(self, base_url: str, timeout: float = 240):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    async def version(self) -> str:
        async with httpx.AsyncClient(timeout=10) as c:
            return (await c.get(f"{self.base}/api/version")).json().get("version", "?")

    async def models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=10) as c:
            return [m["name"] for m in (await c.get(f"{self.base}/api/tags")).json().get("models", [])]

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.post(f"{self.base}/api/embed", json={"model": model, "input": texts})
            r.raise_for_status()
            return r.json()["embeddings"]

    async def chat_json(self, model: str, system: str, user: str, schema: dict, options: dict) -> dict:
        body = {"model": model, "stream": False, "format": schema, "think": False,
                "options": options,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.post(f"{self.base}/api/chat", json=body)
            if r.status_code == 400 and "think" in r.text:
                body.pop("think")
                r = await c.post(f"{self.base}/api/chat", json=body)
            r.raise_for_status()
            content = r.json()["message"]["content"]
        content = re.sub(r"^```(?:json)?|```$", "", content.strip())
        return json.loads(content)


# ------------------------------------------------------------------ assessor

SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "violates": {"type": "boolean"},
                    "design_quote": {"type": "string"},
                    "title": {"type": "string"},
                    "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                    "kind": {"type": "string", "enum": ["wrong", "missing", "risky", "inconsistent"]},
                    "path": {"type": "string"},
                    "evidence_lines": {"type": "array", "items": {"type": "string"}},
                    "expected_lines": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "fix_lines": {"type": "array", "items": {"type": "string"}},
                    "doc_ref": {"type": "string"},
                    "best_practice": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["violates", "design_quote", "title", "severity", "kind", "path",
                             "evidence_lines", "reason", "fix_lines", "doc_ref", "confidence"],
            },
        }
    },
    "required": ["findings"],
}

SYSTEM = """You are a senior Juniper Junos engineer auditing one device's configuration against the
operator's design documents and configuration templates.

Report only real anomalies:
- configuration that contradicts the design extracts or templates provided,
- configuration that is wrong or broken on Junos regardless of design (dangling references,
  objects referenced but not defined, inconsistent values between related statements),
- clear security or resilience risks.

Do not report:
- anything listed under ALREADY REPORTED,
- anything the design explicitly approves,
- style preferences or features the design does not ask for,
- guesses about configuration you cannot see.

Only output problems. Never output configuration that is correct or compliant: if you checked
something and it is fine, leave it out. Set violates=true only for a real problem.

design_quote must be one sentence copied word for word from DESIGN AND TEMPLATE EXTRACTS that the
configuration breaks. If no sentence in the extracts is broken, use design_quote="Junos" and only
report a genuine Junos platform error (dangling reference, undefined object, conflicting values).

Every finding must quote the exact configuration lines it is about in evidence_lines, copied
character for character from the CONFIGURATION section. For a "missing" finding, quote the nearest
related existing lines, and put the lines that should exist in expected_lines.
fix_lines are Junos set/delete/rename commands.
doc_ref names the design section or template rule you relied on (e.g. "HLD-evpn-fabric §7.2"),
or "Junos" for platform correctness issues.

Template placeholders: in the extracts, <per-device value: NAME> and <any value> mark values that
are different on every device (loopbacks, addresses, AS numbers, names). Any concrete value in that
position is compliant. Never report a value because it does not look like the placeholder, and never
put a placeholder or its NAME into fix_lines (for example, never write "lo0:1" for
<per-device value: lo0>:1).

Severity: 5 outage or direct security exposure now; 4 service at risk or material security
weakness; 3 deviation that hurts operations or resilience; 2 hygiene or consistency; 1 advisory.
confidence: 0.9+ only when the evidence is unambiguous.
Return {"findings": []} if there is nothing to report. Respond with JSON only."""

SEC_SCHEMA = copy.deepcopy(SCHEMA)
SEC_SCHEMA["properties"]["findings"]["items"]["required"].append("best_practice")

SEC_SYSTEM = """You are a senior Juniper Junos security engineer auditing one device's running
configuration against the operator's security baseline. Look for security weaknesses: management
plane exposure, missing or weak control-plane protection (loopback filters), unauthenticated routing
protocols, permissive or badly built firewall filters (ACLs), insecure services, SNMP, NTP, logging
gaps and Layer 2 edge protection.

Report only real security gaps:
- configuration that falls short of a statement in SECURITY BASELINE AND TEMPLATE EXTRACTS,
- firewall filters that permit too much (any source to management protocols, permit before a more
  specific deny, no final discard term, no counters),
- clear security risks a Junos security reviewer would raise.

Do not report:
- anything listed under ALREADY REPORTED,
- design, routing or consistency issues that are not security issues,
- guesses about configuration you cannot see. Secrets are masked as SECRET-DATA: a masked value
  means the secret IS configured; never report it as missing or weak.

Only output problems. Set violates=true only for a real gap.

best_practice: one or two sentences stating what good looks like, in operator language.
design_quote must be one sentence copied word for word from SECURITY BASELINE AND TEMPLATE EXTRACTS
that the configuration falls short of. If none applies, use design_quote="Junos" and only report a
clear, specific security risk on Junos.

Every finding must quote the exact configuration lines it is about in evidence_lines, copied
character for character from the CONFIGURATION section. For a "missing" finding, quote the nearest
related existing lines, and put the lines that should exist in expected_lines.
fix_lines are Junos set/delete commands. doc_ref names the baseline section (e.g.
"SEC-baseline-junos §3.1") or "Junos".

Template placeholders: in the extracts, <per-device value: NAME> and <any value> mark values that
are different on every device. Any concrete value in that position is compliant. Never put a
placeholder or its NAME into fix_lines.

Severity: 5 direct exposure now, exploitable without credentials; 4 material weakness an attacker can
use; 3 missing defence in depth or audit; 2 hardening hygiene; 1 advisory.
confidence: 0.9+ only when the evidence is unambiguous.
Return {"findings": []} if there is nothing to report. Respond with JSON only."""

GROUPS = {"system": "system", "snmp": "system", "chassis": "system",
          "interfaces": "interfaces", "vlans": "interfaces", "bridge-domains": "interfaces",
          "multi-chassis": "interfaces",
          "routing-instances": "routing", "protocols": "routing", "policy-options": "routing",
          "routing-options": "routing", "firewall": "routing", "class-of-service": "routing"}
CATEGORY = {"system": "Base", "snmp": "Base", "interfaces": "Infra", "vlans": "Infra",
            "multi-chassis": "Infra", "protocols": "Infra", "routing-instances": "Service",
            "policy-options": "Service", "class-of-service": "Service"}


def chunk_config(lines: list[str], max_lines: int = 140) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for l in lines:
        t = l.split()
        top = t[1] if len(t) > 1 else "other"
        if top == "version":
            continue
        groups[GROUPS.get(top, "other")].append(l)
    out = {}
    for g, ls in groups.items():
        for i in range(0, len(ls), max_lines):
            out[g if i == 0 else f"{g}-{i // max_lines + 1}"] = ls[i:i + max_lines]
    return out


def _norm(s: str) -> str:
    return " ".join(s.strip().strip("`").split())


def _ph_display(text: str) -> str:
    """Show {{name}} placeholders as obvious per-device slots before the LLM sees them."""
    def rep(m):
        n = m.group(1).strip("{} ")
        return "<any value>" if n == "*" else f"<per-device value: {n}>"
    return PH.sub(rep, text)


def _template_patterns(role: str, security: bool | None = None) -> list[tuple]:
    """Every required template line for the role as (full_rx, names, suffix_rx, strict).

    full_rx matches a whole config line. suffix_rx finds the same statement inside a line even
    when the LLM puts it under the wrong hierarchy. Per-device placeholders match any value;
    role/default vars must equal their value. strict = names bound by a block's @scope (e.g. an
    interface), which must be the same thing for two lines to be "the same statement"."""
    try:
        inv, _ = inventory()
        blocks = load_blocks(inv["roles"][role].get("templates", []))
        shared = {**(inv.get("defaults", {}).get("vars") or {}), **(inv["roles"][role].get("vars") or {})}
    except Exception:  # noqa: BLE001
        return []
    out = []
    for b in blocks:
        if security is not None and (b.category == "Security") != security:
            continue
        strict = set(re.findall(r"\(\?P<(\w+)>", b.scope or ""))
        for t in b.required:
            if not t.startswith("set "):
                continue
            rx, names = [], []
            for part in PH.split(t[4:]):
                if PH.fullmatch(part):
                    n = part.strip("{} ")
                    if n == "*":
                        rx.append(".*")
                    elif n in shared:
                        rx.append(re.escape(str(shared[n])))
                    else:
                        rx.append(f"({VALUE})")
                        names.append(n)
                else:
                    rx.append(re.escape(part))
            body = "".join(rx)
            out.append((re.compile("^set " + body + "$"), names, re.compile(r"(?:^|\s)" + body + "$"), strict))
    return out


def _template_required(ev: list[str], pats) -> bool:
    """True if every evidence line is exactly what a template requires (templates outrank the LLM)."""
    return bool(ev) and all(any(p[0].match(e) for p in pats) for e in ev)


def _already_present(fixes: list[str], config: list[str], pats) -> bool:
    """True if every 'set' fix is a template statement the config already satisfies
    (same statement, same scoped object; per-device values may differ)."""
    sets = [x for x in fixes if x.startswith("set ")]
    if not sets:
        return False
    for x in sets:
        hit = False
        for full, names, suf, strict in pats:
            m = suf.search(x)
            if not m:
                continue
            want = {n: v for n, v in zip(names, m.groups()) if n in strict}
            for l in config:
                c = full.match(l)
                if c and all(dict(zip(names, c.groups())).get(n) == v for n, v in want.items()):
                    hit = True
                    break
            if hit:
                break
        if not hit:
            return False
    return True


def _placeholder_problem(ev: list[str], fixes: list[str], pats) -> str:
    """'' if fine, else why the finding is only about a per-device placeholder value."""
    for x in fixes:
        if "{{" in x or "<per-device" in x.lower() or "<any value" in x.lower():
            return "fix contains a placeholder"
        for full, names, suf, strict in pats:
            m = suf.search(x)
            if m and any(v == n or v.startswith((n + ".", n + ":")) for v, n in zip(m.groups(), names)):
                return "fix uses the placeholder name as a value"
    if ev and all(any(p[0].match(e) for p in pats) for e in ev) \
            and all(x.startswith("delete ") or any(p[0].match(x) for p in pats) for x in fixes):
        return "evidence matches a template line; only the per-device value differs"
    return ""


SELF_CLEARED = re.compile(
    r"compliant|already reported|no action|this is correct|is correct\b|appears consistent|"
    r"is consistent|no issue|not an issue|as required|meets the design|matches the design")


def _anchor(line: str) -> str:
    """First three hierarchy tokens of a config statement, e.g. 'interfaces irb unit'→'interfaces irb'."""
    t = _norm(line).replace("/", " ").split()
    if t and t[0] in ("set", "delete", "rename", "deactivate", "activate"):
        t = t[1:]
    return " ".join(t[:2]).lower()


def _noop(fix: str, config_set: set[str]) -> bool:
    """A fix that changes nothing: a 'set' already present, or a rename to the same name."""
    if fix.startswith("set ") and fix in config_set:
        return True
    m = re.match(r"^rename (.+?) (\S+) to (?:\S+ )?(\S+)$", fix) or re.match(r"^set (.+) rename (\S+)$", fix)
    if m:
        toks = fix.split()
        names = [t for t in toks if t not in ("rename", "to", "set")]
        return len(set(names[-2:])) == 1
    return False


def _overlaps(f: Finding, rule_findings: list[Finding]) -> bool:
    ev = {_norm(e.split(": ", 1)[-1]) for e in f.evidence} | {_norm(x) for x in f.fix}
    for r in rule_findings:
        rv = {_norm(e.split(": ", 1)[-1]) for e in r.evidence} | {_norm(x) for x in r.fix}
        if ev & rv:
            return True
        if f.path and r.path and _norm(f.path) == _norm(r.path):
            return True
    return False


async def assess_device(ollama: Ollama, retriever: Retriever, dev: Device, role_desc: str,
                        lines: list[str], rule_findings: list[Finding], cfg: dict,
                        progress=None, mode: str = "design") -> tuple[list[Finding], dict]:
    """mode "design": anomalies against design docs/templates (Anomalies tab).
    mode "security": security gaps against the security baseline (Security tab)."""
    sec = mode == "security"
    system, schema = (SEC_SYSTEM, SEC_SCHEMA) if sec else (SYSTEM, SCHEMA)
    label = "security review" if sec else "reviewing"
    model = cfg["model"]
    opts = {"temperature": cfg.get("temperature", 0.1), "num_ctx": cfg.get("num_ctx", 8192)}
    k = cfg.get("retrieve_k", 4) + (2 if sec else 0)   # the baseline spans more topics per chunk
    min_conf = cfg.get("min_confidence", 0.5)
    config_set = {_norm(l) for l in lines}
    # Templates outrank the LLM, but only templates of the same kind: a design-compliant line can
    # still be a security gap, so the security pass is checked against security templates only.
    tpats = _template_patterns(dev.role, security=sec)
    pats = [p for p in tpats if p[1]]
    cfg_norm = [_norm(l) for l in lines]
    already = "\n".join(f"- {r.title} [{r.path}]" for r in rule_findings) or "- (none)"
    stats = {"chunks": 0, "raw": 0, "kept": 0, "dropped_unverified": 0, "dropped_duplicate": 0,
             "dropped_low_conf": 0, "dropped_compliant": 0, "dropped_ungrounded": 0,
             "dropped_noop": 0, "dropped_placeholder": 0, "dropped_template": 0, "errors": 0,
             "seconds": 0.0}
    out: list[Finding] = []
    t0 = time.time()
    chunks = chunk_config(lines)
    for i, (name, chunk) in enumerate(chunks.items(), 1):
        if progress:
            progress(f"LLM {label} {dev.name} · {name} ({i}/{len(chunks)})")
        stats["chunks"] += 1
        passages = await retriever.search("\n".join(chunk), k=k)
        extracts = _ph_display("\n\n".join(p.text for p in passages)) or "(no design extracts found)"
        user = (f"DEVICE: {dev.name}  ROLE: {dev.role} ({role_desc})  SECTION: {name}\n\n"
                f"{'SECURITY BASELINE' if sec else 'DESIGN'} AND TEMPLATE EXTRACTS:\n{extracts}\n\n"
                f"ALREADY REPORTED (do not repeat):\n{already}\n\n"
                f"CONFIGURATION ({len(chunk)} lines, set format):\n" + "\n".join(chunk))
        try:
            resp = await ollama.chat_json(model, system, user, schema, opts)
        except Exception as e:  # noqa: BLE001
            stats["errors"] += 1
            stats.setdefault("last_error", str(e)[:200])
            continue
        extracts_n = _norm(extracts).lower()
        for raw in resp.get("findings", []):
            stats["raw"] += 1
            conf = float(raw.get("confidence", 0) or 0)
            if conf < min_conf:
                stats["dropped_low_conf"] += 1
                continue
            text = " ".join([raw.get("title", ""), raw.get("reason", ""), raw.get("doc_ref", "")]).lower()
            if (raw.get("violates") is False or SELF_CLEARED.search(text)):
                stats["dropped_compliant"] += 1
                continue
            # Grounding: the quoted design sentence must exist in what the model was given.
            quote = _norm(raw.get("design_quote", "")).strip("\"'. ").lower()
            if quote != "junos" and (len(quote) < 15 or quote not in extracts_n):
                stats["dropped_ungrounded"] += 1
                continue
            ev_ok = [e for e in raw.get("evidence_lines", []) if _norm(e) in config_set]
            kind = raw.get("kind", "wrong")
            if kind != "missing" and not ev_ok:
                stats["dropped_unverified"] += 1
                continue
            fixes = [_norm(x) for x in raw.get("fix_lines", []) if _norm(x)]
            if not fixes or all(_noop(x, config_set) for x in fixes):
                stats["dropped_noop"] += 1
                continue
            # Template placeholders ({{lo0}} etc.) accept any per-device value.
            if pats and _placeholder_problem([_norm(e) for e in ev_ok], fixes, pats):
                stats["dropped_placeholder"] += 1
                continue
            # A line the templates require is compliant by definition: the LLM may not overrule it.
            if kind != "missing" and _template_required([_norm(e) for e in ev_ok], tpats):
                stats["dropped_template"] += 1
                continue
            # "Missing" claims for a template statement the config already satisfies.
            if _already_present(fixes, cfg_norm, tpats):
                stats["dropped_template"] += 1
                continue
            # The fix must touch the same config the evidence is about.
            anchors = {_anchor(e) for e in ev_ok} | {_anchor("set " + raw.get("path", ""))}
            anchors |= {_anchor(e) for e in raw.get("expected_lines", [])}
            anchors.discard("")
            if anchors and not any(_anchor(x) in anchors for x in fixes):
                stats["dropped_unrelated_fix"] = stats.get("dropped_unrelated_fix", 0) + 1
                continue
            path = raw.get("path", "").strip()
            top = (path.split() or [name])[0]
            evidence = [f"CONFLICT: {_norm(e)}" if kind != "missing" else _norm(e) for e in ev_ok]
            evidence += [f"MISSING: {_norm(e)}" for e in raw.get("expected_lines", []) if _norm(e)]
            f = Finding(device=dev.name, role=dev.role,
                        category="Security" if sec else CATEGORY.get(top, "Infra"),
                        practice=raw.get("best_practice", "").strip()[:400],
                        source="LLM", severity=max(1, min(5, int(raw.get("severity", 2)))),
                        title=raw.get("title", "").strip()[:140] or "Unnamed anomaly",
                        path=path[:120], reason=raw.get("reason", "").strip(),
                        evidence=evidence[:20],
                        fix=fixes[:12],
                        doc=raw.get("doc_ref", "").strip()[:120], confidence=round(conf, 2))
            if _overlaps(f, rule_findings) or _overlaps(f, out):
                stats["dropped_duplicate"] += 1
                continue
            out.append(f)
            stats["kept"] += 1
    stats["seconds"] = round(time.time() - t0, 1)
    return out, stats


# ------------------------------------------------------------------ change review

CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "intent": {"type": "string"},
        "risk": {"type": "integer", "minimum": 1, "maximum": 5},
        "concerns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "lines": {"type": "array", "items": {"type": "string"}},
                    "design_quote": {"type": "string"},
                    "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": ["text", "lines", "design_quote", "severity"],
            },
        },
    },
    "required": ["summary", "intent", "risk", "concerns"],
}

CHANGE_SYSTEM = """You are a senior Juniper Junos engineer reviewing a configuration change on one
device. Lines starting with + were added, lines starting with - were removed.

summary: two or three plain sentences saying what the change does, for an operations team.
intent: a few words guessing the purpose (e.g. "enable management service", "remove LLDP").
risk: 1 cosmetic, 2 low, 3 needs review, 4 likely harmful or insecure, 5 outage or exposure now.
concerns: only real problems with this change. Each concern quotes the changed lines it is about,
copied exactly (including the + or -), and gives design_quote: one sentence copied word for word
from DESIGN EXTRACTS that the change breaks, or "Junos" for a platform or security problem.
Do not list a concern for a change that agrees with the design. Respond with JSON only."""


async def review_change(ollama: Ollama, retriever: Retriever, dev: Device, diff: dict, hints: list[dict],
                        commits: list[dict], cfg: dict) -> dict:
    changed = [f"+ {l}" for l in diff["added"]] + [f"- {l}" for l in diff["removed"]]
    shown = changed[:150]
    passages = await retriever.search("\n".join(shown), k=cfg.get("retrieve_k", 4))
    extracts = _ph_display("\n\n".join(p.text for p in passages)) or "(no design extracts found)"
    who = "; ".join(f"{c['time']} by {c['user']} via {c['via']}" + (f" ({c['comment']})" if c.get("comment") else "")
                    for c in commits[:5]) or "unknown"
    user = (f"DEVICE: {dev.name}  ROLE: {dev.role}\nCOMMITS IN THIS WINDOW: {who}\n\n"
            f"DESIGN EXTRACTS:\n{extracts}\n\n"
            f"CHANGE ({len(diff['added'])} added, {len(diff['removed'])} removed"
            + (f", first {len(shown)} shown" if len(shown) < len(changed) else "") + "):\n" + "\n".join(shown))
    opts = {"temperature": cfg.get("temperature", 0.1), "num_ctx": cfg.get("num_ctx", 8192)}
    t0 = time.time()
    resp = await ollama.chat_json(cfg["model"], CHANGE_SYSTEM, user, CHANGE_SCHEMA, opts)
    changed_n = {_norm(x) for x in changed}
    ext_n = _norm(extracts).lower()
    kept, dropped = [], 0
    for c in resp.get("concerns", []):
        lines = [_norm(x) for x in c.get("lines", []) if _norm(x) in changed_n]
        q = _norm(c.get("design_quote", "")).strip("\"'. ").lower()
        grounded = q == "junos" or (len(q) >= 15 and q in ext_n)
        if not lines or not grounded or SELF_CLEARED.search(c.get("text", "").lower()):
            dropped += 1
            continue
        kept.append({"text": c.get("text", "").strip(), "lines": lines[:8],
                     "severity": max(1, min(5, int(c.get("severity", 2)))),
                     "ref": "Junos" if q == "junos" else c.get("design_quote", "").strip()[:200]})
    model_risk = max(1, min(5, int(resp.get("risk", 2))))
    hint_risk = max([h["risk"] for h in hints], default=1)
    concern_risk = max([c["severity"] for c in kept], default=1)
    # Never let the model alone push risk above "needs review" without grounded evidence.
    risk = max(hint_risk, concern_risk, min(model_risk, 3 if kept or hints else 2))
    return {"summary": resp.get("summary", "").strip(), "intent": resp.get("intent", "").strip(),
            "risk": risk, "model_risk": model_risk, "concerns": kept, "dropped": dropped,
            "model": cfg["model"], "seconds": round(time.time() - t0, 1)}
