#!/usr/bin/env python3
"""Check config/inventory.yaml and knowledge/ before a scan.

Run from the repo root (on the VM, inside the backend container):

    docker compose exec backend python scripts/check_knowledge.py
    docker compose exec backend python scripts/check_knowledge.py --test qfx1 /opt/config-check/data/configs/24/qfx1.set

Exit code 0 = no errors (warnings allowed), 1 = errors found.
--test runs the role's rules against a saved config (set format) and lists the findings,
so you can try a new template before the next scan.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("CC_ROOT", str(ROOT))
sys.path.insert(0, str(ROOT))

from app.common import KNOWLEDGE, inventory, load_yaml  # noqa: E402
from app.rules import BUILTINS, PH, load_blocks, run_rules, template_files  # noqa: E402

errors: list[str] = []
warnings: list[str] = []
err = errors.append
warn = warnings.append


def check_inventory() -> tuple[dict, list]:
    inv, devs = inventory()
    roles = inv.get("roles") or {}
    if not roles:
        err("inventory: no roles defined")
    names = Counter(d.name for d in devs)
    for n, c in names.items():
        if c > 1:
            err(f"inventory: device '{n}' appears {c} times (names must be unique)")
    hosts = Counter(d.host for d in devs)
    for h, c in hosts.items():
        if c > 1:
            warn(f"inventory: host {h} is used by {c} devices")
    for d in devs:
        if not d.host:
            err(f"inventory: device '{d.name}' has no host")
    for rname, r in roles.items():
        tmpl = r.get("templates") or []
        if not tmpl:
            warn(f"role {rname}: no templates (only drift and the LLM will check it)")
        for sel in tmpl:
            if not template_files([sel]):
                err(f"role {rname}: template '{sel}' not found under knowledge/templates/ "
                    f"(a folder name or a file name without .set)")
        for key in ("design", "security"):
            if key in r:
                for doc in r.get(key) or []:
                    if not (KNOWLEDGE / doc).is_file():
                        err(f"role {rname}: {key} doc '{doc}' not found under knowledge/")
            elif key == "design":
                warn(f"role {rname}: no 'design' list, so the LLM will use EVERY doc in knowledge/design/")
        for pat in r.get("drift_ignore") or []:
            try:
                re.compile(pat)
            except re.error as e:
                err(f"role {rname}: bad drift_ignore regex {pat!r}: {e}")
        if not (r.get("devices") or {}):
            warn(f"role {rname}: no devices")
        peer = (r.get("vars") or {}).get("peer_role")
        if peer and peer not in roles:
            err(f"role {rname}: vars.peer_role '{peer}' is not a role")
    return inv, devs


def check_templates(inv: dict, devs: list) -> None:
    ids: dict[str, str] = {}
    files = sorted((KNOWLEDGE / "templates").rglob("*.set"))
    for f in files:
        rel = f.relative_to(KNOWLEDGE)
        for b in load_blocks([str(f.relative_to(KNOWLEDGE / "templates").with_suffix(""))]):
            where = f"{rel} [{b.id}]"
            if b.id in ids:
                err(f"{where}: @id already used in {ids[b.id]} (ids must be unique; renaming one resets its exceptions)")
            ids.setdefault(b.id, str(rel))
            if not (1 <= b.sev <= 5):
                err(f"{where}: @sev must be 1-5")
            if not b.title:
                err(f"{where}: missing @title")
            if not b.doc:
                warn(f"{where}: no @doc reference")
            if b.category == "Security" and not b.practice:
                warn(f"{where}: security rule without @practice (no best-practice text on the dashboard)")
            if b.builtin and b.builtin not in BUILTINS:
                err(f"{where}: unknown @builtin '{b.builtin}' (known: {', '.join(sorted(BUILTINS))})")
            if not b.builtin and not (b.required or b.forbidden):
                err(f"{where}: block has no set/!set lines and no @builtin")
            scope_names = set()
            if b.scope:
                try:
                    scope_names = set(re.compile(b.scope).groupindex)
                except re.error as e:
                    err(f"{where}: bad @scope regex: {e}")
            for line in b.required + b.forbidden:
                if not line.startswith("set "):
                    err(f"{where}: line must start with 'set ' or '!set ': {line!r}")
                for ph in PH.findall(line):
                    n = ph.strip("{} ")
                    if n == "*" or n in scope_names:
                        continue
                    # resolvable for every device that uses this file?
                    users = [d for d in devs if any(
                        f in template_files([s]) for s in inv["roles"][d.role].get("templates", []))]
                    missing = [d.name for d in users if n not in d.vars]
                    if missing and len(missing) == len(users):
                        warn(f"{where}: {{{{{n}}}}} is not an inventory var for any device, so it matches any value")
                    elif missing:
                        warn(f"{where}: {{{{{n}}}}} has no value for {', '.join(missing)}, so it matches any value there")
    print(f"templates: {len(files)} files, {len(ids)} rules")


def check_docs() -> None:
    for f in sorted([*(KNOWLEDGE / "design").rglob("*"), *(KNOWLEDGE / "security").rglob("*")]):
        if f.is_dir():
            continue
        if f.suffix.lower() not in (".md", ".txt"):
            warn(f"{f.relative_to(KNOWLEDGE)}: only .md/.txt are read; convert this file to Markdown")
            continue
        text = f.read_text(errors="replace")
        heads = re.findall(r"^#{1,4}\s+(.*)", text, flags=re.M)
        if not heads:
            warn(f"{f.relative_to(KNOWLEDGE)}: no headings, so it becomes one large passage (split it with ## headings)")
        elif not any(re.match(r"\d+(\.\d+)*\s", h) for h in heads):
            warn(f"{f.relative_to(KNOWLEDGE)}: headings are not numbered, so findings can't cite §sections")


def test_device(name: str, cfg: Path) -> None:
    inv, devs = inventory()
    dev = next((d for d in devs if d.name == name), None)
    if not dev:
        sys.exit(f"device {name} not in inventory")
    lines = [l.strip() for l in cfg.read_text().splitlines() if l.startswith("set ")]
    fs = run_rules(dev, lines, load_blocks(inv["roles"][dev.role].get("templates", [])))
    print(f"\n{name} ({dev.role}): {len(fs)} rule findings from {cfg}")
    for f in sorted(fs, key=lambda f: (-f.severity, f.category, f.rule_id)):
        print(f"  S{f.severity} {f.category:8} {f.rule_id:20} {f.title}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", nargs=2, metavar=("DEVICE", "CONFIG_SET_FILE"))
    a = ap.parse_args()
    load_yaml(ROOT / "config" / "settings.yaml")  # parse check
    inv, devs = check_inventory()
    print(f"inventory: {len(inv.get('roles', {}))} roles, {len(devs)} devices")
    check_templates(inv, devs)
    check_docs()
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    if a.test:
        test_device(a.test[0], Path(a.test[1]))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
