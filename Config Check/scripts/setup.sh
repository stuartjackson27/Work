#!/usr/bin/env bash
# First-time setup of Config Check on a fresh Ubuntu VM with Docker installed.
# Run from the repo root:  ./scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p secrets data && chmod 700 secrets
[ -d mcp/junos-mcp-server ] || git clone --depth 1 https://github.com/Juniper/junos-mcp-server mcp/junos-mcp-server

# 1. SSH key the MCP server uses to log in to devices (read-only user "configcheck")
if [ ! -f secrets/configcheck_ed25519 ]; then
  ssh-keygen -t ed25519 -N "" -C "configcheck@config-check" -f secrets/configcheck_ed25519
  echo ">> Add this public key to every device (see docs/DEVICE-PREP.md):"
  cat secrets/configcheck_ed25519.pub
fi

# 2. devices.json for the MCP server, generated from config/inventory.yaml
python3 scripts/gen_devices.py

# 3. Bearer token for backend -> MCP server
docker compose build junos-mcp
if [ ! -f secrets/jmcp-tokens.json ]; then
  out=$(docker run --rm -v "$PWD/secrets:/out" config-check/junos-mcp:local sh -c \
        'python jmcp_token_manager.py generate --id config-check-backend --description "Config Check backend" && cp .tokens /out/jmcp-tokens.json')
  echo "$out"
  tok=$(echo "$out" | grep -oE '[A-Za-z0-9_-]{32,}' | head -1 || true)
  if [ -n "$tok" ]; then printf '%s' "$tok" > secrets/jmcp-backend.token
  else echo ">> Could not auto-detect the token: paste it into secrets/jmcp-backend.token"; fi
fi
chmod 600 secrets/* || true
# Containers run as uid 1000 (backend) - make data writable and the token readable
sudo chown -R 1000:1000 data secrets 2>/dev/null || true

docker compose up -d --build
echo ">> Dashboard: http://$(hostname -I | awk '{print $1}'):8080"
