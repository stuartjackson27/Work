#!/usr/bin/env python3
"""Generate the Junos MCP devices.json from config/inventory.yaml."""
import json, sys, yaml
from pathlib import Path
root = Path(__file__).resolve().parent.parent
inv = yaml.safe_load((root / "config/inventory.yaml").read_text())
d = inv.get("defaults", {})
out = {}
for role, r in inv["roles"].items():
    for name, dev in r["devices"].items():
        out[name] = {
            "ip": dev["host"],
            "port": int(dev.get("port", d.get("port", 830))),
            "username": dev.get("username", d["username"]),
            "auth": {"type": "ssh_key",
                     "private_key_path": dev.get("key_file", d["key_file"])},
        }
dst = root / "config/devices.json"
dst.write_text(json.dumps(out, indent=2) + "\n")
print(f"wrote {dst} ({len(out)} devices)")
