"""Config Check API + dashboard."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import store
from .common import inventory, settings
from .llm import Ollama
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


@app.get("/api/models")
async def get_models():
    """Models the dashboard may offer: llm.allowed_models, marked with whether Ollama has them."""
    lc = settings().get("llm", {})
    allowed = lc.get("allowed_models", [])
    installed, error = set(), ""
    try:
        installed = set(await Ollama(lc.get("base_url", ""), 5).models())
    except Exception as e:  # Ollama down: still list the allowed models
        error = f"Couldn't reach Ollama at {lc.get('base_url', '?')}: {type(e).__name__}"
    has = lambda m: m in installed or f"{m}:latest" in installed
    return {"default": lc.get("model"), "enabled": lc.get("enabled", True), "error": error,
            "models": [{"name": m, "installed": has(m) if installed else None} for m in allowed]}


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


class ScanRequest(BaseModel):
    anomalies: bool = True   # design templates, drift, LLM design review, change reviews
    security: bool = True    # security templates + LLM security review
    llm: bool = True         # LLM review
    rules: bool = True       # rule engine: templates + drift
    model: str | None = None # LLM model for this scan; must be in llm.allowed_models


@app.post("/api/scan")
async def start_scan(req: ScanRequest | None = None):
    req = req or ScanRequest()
    if not (req.anomalies or req.security):
        raise HTTPException(400, "Pick at least one of anomalies or security.")
    if not (req.rules or req.llm):
        raise HTTPException(400, "Pick at least one of rules or LLM.")
    lc = settings().get("llm", {})
    if req.model and req.model not in lc.get("allowed_models", []):
        raise HTTPException(400, f"Model {req.model} is not in llm.allowed_models in settings.yaml.")
    if not req.rules and not (lc.get("enabled", True) and (req.model or lc.get("model")) in lc.get("allowed_models", [])):
        raise HTTPException(400, "The LLM is disabled or its model isn't allowed in settings.yaml, so an LLM-only scan would do nothing.")
    if scanner.start(req.anomalies, req.security, req.llm, req.rules, req.model) is None:
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
