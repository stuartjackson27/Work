"""Scan orchestration: collect → rules → drift → LLM → store."""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path

from . import store
from .changes import commits_between, diff_configs, parse_commits, risk_hints
from .collector import MCPCollector
from .common import DATA, inventory, settings
from .knowledge import Retriever, design_files
from .llm import Ollama, assess_device, review_change
from .rules import load_blocks, role_drift, run_rules

log = logging.getLogger("config-check")


class Scanner:
    def __init__(self):
        self.task: asyncio.Task | None = None
        self.progress = {"running": False, "stage": "idle", "pct": 0, "message": "", "scan_id": None}

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    def start(self) -> int | None:
        if self.running:
            return None
        self.progress = {"running": True, "stage": "starting", "pct": 1, "message": "Starting scan",
                         "scan_id": None, "started": time.time()}
        self.task = asyncio.create_task(self._run())
        return 0

    def _p(self, stage: str, pct: float, message: str):
        self.progress.update(stage=stage, pct=int(pct), message=message)
        log.info("[%s %d%%] %s", stage, pct, message)

    async def _run(self):
        cfg = settings()
        inv, devices = inventory()
        llm_cfg = cfg.get("llm", {})
        model = llm_cfg.get("model", "")
        use_llm = llm_cfg.get("enabled", True)
        if use_llm and model not in llm_cfg.get("allowed_models", []):
            use_llm = False
        sel = sorted({t for r in inv["roles"].values() for t in r.get("templates", [])})
        scan_id = store.new_scan(model if use_llm else "rules only", ", ".join(sel))
        self.progress["scan_id"] = scan_id
        stats: dict = {"devices": len(devices), "llm": {}}
        errors: list[str] = []
        try:
            # 1. collect
            token = Path(cfg["mcp"]["token_file"]).read_text().strip()
            configs: dict[str, list[str]] = {}
            commit_log: dict[str, list[dict]] = {}
            outdir = DATA / "configs" / str(scan_id)
            outdir.mkdir(parents=True, exist_ok=True)
            async with MCPCollector(cfg["mcp"]["url"], token).connect() as mcp:
                for i, d in enumerate(devices):
                    self._p("collect", 2 + 23 * i / max(1, len(devices)), f"Collecting {d.name} ({d.host})")
                    try:
                        lines = await asyncio.wait_for(mcp.config(d.name), cfg["mcp"].get("timeout_s", 120))
                        facts = await asyncio.wait_for(mcp.facts(d.name), 60)
                        configs[d.name] = lines
                        (outdir / f"{d.name}.set").write_text("\n".join(lines) + "\n")
                        try:
                            ctext = await asyncio.wait_for(mcp.commits(d.name), 60)
                            commit_log[d.name] = parse_commits(ctext)
                            store.save_commits(scan_id, d.name, commit_log[d.name])
                        except Exception as e:  # noqa: BLE001
                            log.warning("commit history for %s failed: %s", d.name, e)
                        store.save_device(scan_id, device=d.name, role=d.role, host=d.host,
                                          model=facts.get("model") or d.model, version=facts.get("version", ""),
                                          status="ok", lines=len(lines))
                    except Exception as e:  # noqa: BLE001
                        msg = f"{type(e).__name__}: {e}"[:300]
                        errors.append(f"{d.name}: {msg}")
                        store.save_device(scan_id, device=d.name, role=d.role, host=d.host, model=d.model,
                                          status="unreachable", error=msg)
            if not configs:
                raise RuntimeError("no device configuration could be collected")

            # 2. rules + drift
            self._p("rules", 28, "Checking templates")
            findings = []
            rule_by_dev: dict[str, list] = {}
            for d in devices:
                if d.name not in configs:
                    continue
                blocks = load_blocks(inv["roles"][d.role].get("templates", []))
                rule_by_dev[d.name] = run_rules(d, configs[d.name], blocks)
                findings += rule_by_dev[d.name]
            for role, r in inv["roles"].items():
                rc = {n: configs[n] for n in (r.get("devices") or {}) if n in configs}
                drift = role_drift(role, rc, r.get("drift_ignore", []), {})
                findings += drift
                for f in drift:
                    rule_by_dev.setdefault(f.device, []).append(f)
            stats["rule_findings"] = len(findings)

            # 2b. config history: diff against previous good scan, and against a pinned baseline
            self._p("history", 30, "Comparing with previous snapshots")
            pending: dict[str, list[dict]] = {}
            now_iso = store.scan_time(scan_id)
            for d in devices:
                if d.name not in configs:
                    continue
                bases = []
                prev = store.previous_good(d.name, scan_id)
                if prev:
                    bases.append(("previous", prev["id"], prev["started"]))
                bl = store.baseline(d.name)
                if bl and (not prev or bl["scan_id"] != prev["id"]):
                    bases.append(("baseline", bl["scan_id"], store.scan_time(bl["scan_id"])))
                for kind, bid, btime in bases:
                    f = DATA / "configs" / str(bid) / f"{d.name}.set"
                    if not f.exists():
                        continue
                    diff = diff_configs(f.read_text().splitlines(), configs[d.name])
                    if not (diff["added"] or diff["removed"]):
                        continue
                    pending.setdefault(d.name, []).append({
                        "kind": kind, "base": bid, "base_time": btime, "diff": diff,
                        "commits": commits_between(commit_log.get(d.name, []), btime, now_iso),
                        "hints": risk_hints(diff["added"], diff["removed"]), "review": None})
            stats["changes"] = {k: [{"kind": c["kind"], "added": len(c["diff"]["added"]),
                                     "removed": len(c["diff"]["removed"])} for c in v]
                                for k, v in pending.items()}

            # 3. LLM
            if use_llm:
                ollama = Ollama(llm_cfg["base_url"], llm_cfg.get("timeout_s", 240))
                try:
                    self._p("llm", 32, f"Connecting to Ollama ({model})")
                    await ollama.version()
                    work = [d for d in devices if d.name in configs]
                    for i, d in enumerate(work):
                        role = inv["roles"][d.role]
                        all_blocks = load_blocks(role.get("templates", []))
                        retr = Retriever(ollama, llm_cfg.get("embed_model", "nomic-embed-text"))
                        n = await retr.build(design_files(role.get("design")),
                                             [b for b in all_blocks if b.category != "Security"])
                        base = 35 + 60 * i / len(work)

                        def prog(msg, base=base):
                            self._p("llm", base, msg)
                        for ch in pending.get(d.name, []):
                            if ch["kind"] != "previous":
                                continue
                            prog(f"LLM reviewing changes on {d.name}")
                            try:
                                ch["review"] = await review_change(ollama, retr, d, ch["diff"], ch["hints"],
                                                                   ch["commits"], llm_cfg)
                            except Exception as e:  # noqa: BLE001
                                ch["review"] = {"error": str(e)[:200]}
                        llm_f, st = await assess_device(ollama, retr, d, role.get("description", ""),
                                                        configs[d.name], rule_by_dev.get(d.name, []),
                                                        llm_cfg, prog)
                        st["passages"] = n
                        stats["llm"][d.name] = st
                        findings += llm_f
                        # Security review: same config, checked against the security baseline only.
                        sec_blocks = [b for b in all_blocks if b.category == "Security"]
                        if role.get("security") or sec_blocks:
                            sretr = Retriever(ollama, llm_cfg.get("embed_model", "nomic-embed-text"))
                            sn = await sretr.build(design_files(role["security"]) if role.get("security") else [], sec_blocks)
                            sec_f, sst = await assess_device(
                                ollama, sretr, d, role.get("description", ""), configs[d.name],
                                rule_by_dev.get(d.name, []), llm_cfg, prog, mode="security")
                            sst["passages"] = sn
                            stats.setdefault("llm_security", {})[d.name] = sst
                            findings += sec_f
                except Exception as e:  # noqa: BLE001
                    errors.append(f"LLM: {type(e).__name__}: {e}"[:300])
                    stats["llm"]["error"] = str(e)[:300]

            self._p("store", 97, "Saving findings")
            store.save_findings(scan_id, findings)
            for dev, chs in pending.items():
                for ch in chs:
                    store.save_change(scan_id, dev, ch["kind"], ch["base"], ch["base_time"], ch["diff"],
                                      ch["commits"], ch["hints"], ch["review"])
            removed = store.prune(int(cfg.get("retention", {}).get("scans", 50)))
            for sid in removed:
                shutil.rmtree(DATA / "configs" / str(sid), ignore_errors=True)
            stats["findings"] = len(findings)
            status = "partial" if errors else "complete"
            store.finish_scan(scan_id, status, stats, "; ".join(errors))
            self._p("done", 100, f"Scan complete · {len(configs)} devices · {len(findings)} findings"
                    + (f" · {len(errors)} warning(s)" if errors else ""))
        except Exception as e:  # noqa: BLE001
            log.exception("scan failed")
            store.finish_scan(scan_id, "failed", stats, f"{type(e).__name__}: {e}"[:500])
            self._p("failed", 100, f"Scan failed: {e}")
        finally:
            self.progress["running"] = False
