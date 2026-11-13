"""Smoke test: Junos MCP server reachable, read tools work, write paths blocked."""
import asyncio, json, os
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
URL = os.environ.get("MCP_URL", "http://127.0.0.1:30030/mcp/")
TOKEN = open("/secrets/jmcp-backend.token").read().strip()
def txt(r): return "\n".join(c.text for c in r.content if hasattr(c, "text"))
async def main():
    async with streamablehttp_client(URL, headers={"Authorization": f"Bearer {TOKEN}"}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            print("TOOLS:", ", ".join(tools))
            print("ROUTERS:", txt(await s.call_tool("get_router_list", {}))[:200])
            print("FACTS qfx1:", txt(await s.call_tool("gather_device_facts", {"router_name": "qfx1"}))[:0])
            cfg = txt(await s.call_tool("get_junos_config", {"router_name": "qfx1"}))
            print(f"CONFIG qfx1: {len(cfg.splitlines())} lines; first: {cfg.splitlines()[0][:80] if cfg else ''}")
            print("SHOW (allowed):", txt(await s.call_tool("execute_junos_command", {"router_name": "qfx1", "command": "show system uptime"}))[:160].replace("\n"," | "))
            print("REBOOT (blocked?):", txt(await s.call_tool("execute_junos_command", {"router_name": "qfx1", "command": "request system reboot"}))[:160])
            print("COMMIT (blocked?):", txt(await s.call_tool("load_and_commit_config", {"router_name": "qfx1", "config_text": "set system host-name QFX1", "config_format": "set"}))[:160])
asyncio.run(main())
