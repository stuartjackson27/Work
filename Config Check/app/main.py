"""Config Check API + dashboard."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import store
from .common import inventory, settings
from .scanner import Scanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
app = FastAPI(title="Config Check")
scanner = Scanner()
STATIC = Path(__file__).parent / "static"


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "scanning": scanner.running}


@app.get("/api/state")
def get_state(scan: int | None = None):
    inv, devices = inventory()
    s = settings()
    data = store.state(scan)
    data["roles"] = {r: {"description": v.get("description", ""), "templates": v.get("templates", []),
                         "devices": list((v.get("devices") or {}).keys())}
                     for r, v in inv.get("roles", {}).items()}
    data["inventory"] = [{"name": d.name, "role": d.role, "host": d.host, "model": d.model} for d in devices]
    data["llm"] = {"model": s.get("llm", {}).get("model"), "enabled": s.get("llm", {}).get("enabled", True)}
    data["weights"] = s.get("scoring", {}).get("weights", [0, 1, 2, 4, 7, 12])
    data["progress"] = scanner.progress
    return data


@app.post("/api/scan")
async def start_scan():
    if scanner.start() is None:
        return JSONResponse({"error": "A scan is already running."}, status_code=409)
    return {"started": True}


@app.get("/api/progress")
def progress():
    return scanner.progress


class Decision(BaseModel):
    state: str          # accepted | open
    note: str = ""


class Baseline(BaseModel):
    scan_id: int | None = None   # None unpins
    note: str = ""


@app.post("/api/baseline/{device}")
def pin_baseline(device: str, b: Baseline):
    store.set_baseline(device, b.scan_id, b.note)
    return {"ok": True}


@app.post("/api/findings/{fingerprint}/state")
def decide(fingerprint: str, d: Decision):
    if d.state not in ("accepted", "open"):
        raise HTTPException(400, "state must be 'accepted' or 'open'")
    store.set_decision(fingerprint, d.state, d.note)
    return {"ok": True}
