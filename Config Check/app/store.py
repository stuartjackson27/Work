"""SQLite storage for scans, findings and analyst decisions."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .common import DATA, Finding

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT, status TEXT,
  model TEXT, templates TEXT, stats TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS scan_devices (
  scan_id INTEGER, device TEXT, role TEXT, host TEXT, model TEXT, version TEXT,
  status TEXT, error TEXT, lines INTEGER, PRIMARY KEY (scan_id, device));
CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id INTEGER, fingerprint TEXT, device TEXT, role TEXT,
  category TEXT, source TEXT, severity INTEGER, title TEXT, path TEXT, reason TEXT,
  evidence TEXT, fix TEXT, doc TEXT, rule_id TEXT, confidence REAL, practice TEXT DEFAULT '',
  from_scan INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_findings_scan ON findings(scan_id);
CREATE TABLE IF NOT EXISTS decisions (
  fingerprint TEXT PRIMARY KEY, state TEXT, note TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS commits (
  scan_id INTEGER, device TEXT, data TEXT, PRIMARY KEY (scan_id, device));
CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id INTEGER, device TEXT, kind TEXT,
  base_scan_id INTEGER, base_time TEXT, added TEXT, removed TEXT, sections TEXT,
  commits TEXT, hints TEXT, review TEXT);
CREATE INDEX IF NOT EXISTS ix_changes_scan ON changes(scan_id);
CREATE TABLE IF NOT EXISTS baselines (
  device TEXT PRIMARY KEY, scan_id INTEGER, pinned TEXT, note TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DATA / "config-check.db")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    cols = {r[1] for r in c.execute("PRAGMA table_info(findings)")}
    if "practice" not in cols:
        c.execute("ALTER TABLE findings ADD COLUMN practice TEXT DEFAULT ''")
    if "from_scan" not in cols:
        c.execute("ALTER TABLE findings ADD COLUMN from_scan INTEGER DEFAULT 0")
    return c


def new_scan(model: str, templates: str) -> int:
    with db() as c:
        return c.execute("INSERT INTO scans(started,status,model,templates) VALUES(?,?,?,?)",
                         (now(), "running", model, templates)).lastrowid


def finish_scan(scan_id: int, status: str, stats: dict, error: str = "") -> None:
    with db() as c:
        c.execute("UPDATE scans SET finished=?, status=?, stats=?, error=? WHERE id=?",
                  (now(), status, json.dumps(stats), error, scan_id))


def save_device(scan_id: int, **d) -> None:
    with db() as c:
        c.execute("INSERT OR REPLACE INTO scan_devices VALUES(?,?,?,?,?,?,?,?,?)",
                  (scan_id, d["device"], d["role"], d["host"], d.get("model", ""), d.get("version", ""),
                   d["status"], d.get("error", ""), d.get("lines", 0)))


def save_findings(scan_id: int, findings: list[Finding]) -> None:
    with db() as c:
        c.executemany(
            "INSERT INTO findings(scan_id,fingerprint,device,role,category,source,severity,title,path,"
            "reason,evidence,fix,doc,rule_id,confidence,practice) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(scan_id, f.fingerprint, f.device, f.role, f.category, f.source, f.severity, f.title, f.path,
              f.reason, json.dumps(f.evidence), json.dumps(f.fix), f.doc, f.rule_id, f.confidence,
              f.practice)
             for f in findings])


FIELDS = ("fingerprint,device,role,category,source,severity,title,path,reason,evidence,fix,doc,"
          "rule_id,confidence,practice")


def carry_findings(scan_id: int, device: str, security: bool, source: str) -> tuple[int, list[int]]:
    """Copy one part of a device's findings (security or anomalies, Rule or LLM) from its previous
    good scan into this scan, for a part that was not run. Keeps the scan the findings were first
    produced in (from_scan). Returns (rows copied, ids of the scans the copied findings came from)."""
    prev = previous_good(device, scan_id)
    if not prev:
        return 0, []
    dom = "category='Security'" if security else "category!='Security'"
    with db() as c:
        n = c.execute(
            f"INSERT INTO findings(scan_id,{FIELDS},from_scan) SELECT ?,{FIELDS},"
            f"CASE WHEN from_scan>0 THEN from_scan ELSE scan_id END FROM findings "
            f"WHERE scan_id=? AND device=? AND source=? AND {dom}",
            (scan_id, prev["id"], device, source)).rowcount
        orig = [r[0] for r in c.execute(
            f"SELECT DISTINCT from_scan FROM findings WHERE scan_id=? AND device=? AND source=? AND {dom}",
            (scan_id, device, source))]
    return n, orig


def set_decision(fp: str, state: str, note: str = "") -> None:
    with db() as c:
        if state == "open":
            c.execute("DELETE FROM decisions WHERE fingerprint=?", (fp,))
        else:
            c.execute("INSERT OR REPLACE INTO decisions VALUES(?,?,?,?)", (fp, state, note, now()))


def state(scan_id: int | None = None) -> dict:
    c = db()
    scans = [dict(r) for r in c.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 20")]
    done = [s for s in scans if s["status"] in ("complete", "partial")]
    if scan_id is None:
        scan = done[0] if done else None
    else:
        scan = next((s for s in scans if s["id"] == scan_id), None)
    decisions = {r["fingerprint"]: dict(r) for r in c.execute("SELECT * FROM decisions")}
    trend = []
    for s in reversed(done[:8]):
        rows = c.execute("SELECT fingerprint, category FROM findings WHERE scan_id=?", (s["id"],)).fetchall()
        trend.append({"scan": s["id"],
                      "open": sum(1 for f, cat in rows if f not in decisions and cat != "Security"),
                      "security": sum(1 for f, cat in rows if f not in decisions and cat == "Security")})
    if not scan:
        return {"scan": None, "devices": [], "findings": [], "trend": trend, "scans": scans}
    # Per device: fingerprints in its previous good scan, and in any earlier good scan.
    prev_fps: dict[str, set] = {}
    older_fps: dict[str, set] = {}
    for d in c.execute("SELECT DISTINCT device FROM scan_devices WHERE scan_id=?", (scan["id"],)):
        dev = d[0]
        ok = [r[0] for r in c.execute(
            "SELECT sd.scan_id FROM scan_devices sd JOIN scans s ON s.id=sd.scan_id "
            "WHERE sd.device=? AND sd.status='ok' AND sd.scan_id<? AND s.status IN ('complete','partial') "
            "ORDER BY sd.scan_id DESC", (dev, scan["id"]))]
        prev_fps[dev] = set()
        older_fps[dev] = set()
        if ok:
            prev_fps[dev] = {r[0] for r in c.execute(
                "SELECT fingerprint FROM findings WHERE scan_id=? AND device=?", (ok[0], dev))}
            if len(ok) > 1:
                q = ",".join("?" * len(ok[1:]))
                older_fps[dev] = {r[0] for r in c.execute(
                    f"SELECT fingerprint FROM findings WHERE device=? AND scan_id IN ({q})", (dev, *ok[1:]))}
    findings = []
    for r in c.execute("SELECT * FROM findings WHERE scan_id=? ORDER BY severity DESC, device", (scan["id"],)):
        f = dict(r)
        f["evidence"] = json.loads(f["evidence"])
        f["fix"] = json.loads(f["fix"])
        d = decisions.get(f["fingerprint"])
        fp, dev = f["fingerprint"], f["device"]
        if d:
            f["state"] = "accepted"
        elif fp in prev_fps.get(dev, set()):
            f["state"] = "recurring"
        elif fp in older_fps.get(dev, set()):
            f["state"] = "regressed"
        else:
            f["state"] = "new"
        f["note"] = d["note"] if d else ""
        findings.append(f)
    devices = [dict(r) for r in c.execute("SELECT * FROM scan_devices WHERE scan_id=? ORDER BY device",
                                           (scan["id"],))]
    changes = []
    for r in c.execute("SELECT * FROM changes WHERE scan_id=? ORDER BY device, kind", (scan["id"],)):
        ch = dict(r)
        for k in ("added", "removed", "sections", "commits", "hints", "review"):
            ch[k] = json.loads(ch[k] or "null")
        changes.append(ch)
    commits = {r["device"]: json.loads(r["data"]) for r in
               c.execute("SELECT * FROM commits WHERE scan_id=?", (scan["id"],))}
    baselines = {r["device"]: dict(r) for r in c.execute("SELECT * FROM baselines")}
    scan = {**scan, "stats": json.loads(scan["stats"] or "{}")}
    return {"scan": scan, "devices": devices, "findings": findings, "trend": trend, "scans": scans,
            "changes": changes, "commits": commits, "baselines": baselines}


# ------------------------------------------------------------------ history

def save_commits(scan_id: int, device: str, commits: list[dict]) -> None:
    with db() as c:
        c.execute("INSERT OR REPLACE INTO commits VALUES(?,?,?)", (scan_id, device, json.dumps(commits)))


def save_change(scan_id: int, device: str, kind: str, base_scan_id: int, base_time: str, diff: dict,
                commits: list[dict], hints: list[dict], review: dict | None) -> None:
    with db() as c:
        c.execute("INSERT INTO changes(scan_id,device,kind,base_scan_id,base_time,added,removed,sections,"
                  "commits,hints,review) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (scan_id, device, kind, base_scan_id, base_time, json.dumps(diff["added"]),
                   json.dumps(diff["removed"]), json.dumps(diff["sections"]), json.dumps(commits),
                   json.dumps(hints), json.dumps(review)))


def previous_good(device: str, before_scan: int) -> dict | None:
    """Most recent earlier scan where this device was collected."""
    r = db().execute(
        "SELECT s.id, s.started FROM scans s JOIN scan_devices sd ON sd.scan_id=s.id "
        "WHERE sd.device=? AND sd.status='ok' AND s.id<? AND s.status IN ('complete','partial') "
        "ORDER BY s.id DESC LIMIT 1", (device, before_scan)).fetchone()
    return dict(r) if r else None


def scan_time(scan_id: int) -> str:
    r = db().execute("SELECT started FROM scans WHERE id=?", (scan_id,)).fetchone()
    return r[0] if r else ""


def baseline(device: str) -> dict | None:
    r = db().execute("SELECT * FROM baselines WHERE device=?", (device,)).fetchone()
    return dict(r) if r else None


def set_baseline(device: str, scan_id: int | None, note: str = "") -> None:
    with db() as c:
        if scan_id is None:
            c.execute("DELETE FROM baselines WHERE device=?", (device,))
        else:
            c.execute("INSERT OR REPLACE INTO baselines VALUES(?,?,?,?)", (device, scan_id, now(), note))


def prune(keep: int) -> list[int]:
    """Delete scans beyond the newest `keep`, never deleting a pinned baseline scan."""
    with db() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM scans ORDER BY id DESC")]
        pinned = {r[0] for r in c.execute("SELECT scan_id FROM baselines")}
        old = [i for i in ids[keep:] if i not in pinned]
        for i in old:
            for t in ("findings", "scan_devices", "changes", "commits"):
                c.execute(f"DELETE FROM {t} WHERE scan_id=?", (i,))
            c.execute("DELETE FROM scans WHERE id=?", (i,))
    return old
