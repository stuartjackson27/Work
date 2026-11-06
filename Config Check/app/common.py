"""Shared paths, config loading and the Finding model."""
from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("CC_ROOT", "/opt/config-check"))
CONFIG = ROOT / "config"
KNOWLEDGE = ROOT / "knowledge"
DATA = ROOT / "data"

SEV_NAMES = {5: "Critical", 4: "High", 3: "Medium", 2: "Low", 1: "Info"}


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def settings() -> dict:
    return load_yaml(CONFIG / "settings.yaml")


@dataclass
class Device:
    name: str
    role: str
    host: str
    model: str = ""
    vars: dict = field(default_factory=dict)


def inventory() -> tuple[dict, list[Device]]:
    inv = load_yaml(CONFIG / "inventory.yaml")
    dvars = inv.get("defaults", {}).get("vars", {}) or {}
    devices = []
    for role, r in inv.get("roles", {}).items():
        rvars = {**dvars, **(r.get("vars") or {})}
        for name, d in (r.get("devices") or {}).items():
            devices.append(Device(name=name, role=role, host=d["host"],
                                  model=d.get("model", ""), vars={**rvars, **(d.get("vars") or {})}))
    return inv, devices


@dataclass
class Finding:
    device: str
    role: str
    category: str          # Base | Infra | Service | Drift
    source: str            # Rule | LLM
    severity: int          # 1..5
    title: str
    path: str              # config hierarchy the finding is about
    reason: str
    evidence: list[str] = field(default_factory=list)   # config lines; "- ..." = missing
    fix: list[str] = field(default_factory=list)
    doc: str = ""
    rule_id: str = ""
    confidence: float = 1.0
    practice: str = ""     # best practice the finding is measured against (Security tab)

    @property
    def fingerprint(self) -> str:
        key = self.rule_id or " ".join(self.title.lower().split())
        raw = f"{self.device}|{self.source}|{key}|{self.path}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fingerprint"] = self.fingerprint
        return d
