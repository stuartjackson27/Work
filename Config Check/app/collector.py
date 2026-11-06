"""Collect configs and facts from devices through the Junos MCP server (read-only tools only)."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager


# The backend never calls anything outside this list, even though the server exposes more.
ALLOWED_TOOLS = {"get_junos_config", "gather_device_facts", "execute_junos_command", "get_router_list"}


class MCPCollector:
    def __init__(self, url: str, token: str):
        self.url, self.token = url, token
        self.session = None

    @asynccontextmanager
    async def connect(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(self.url, headers={"Authorization": f"Bearer {self.token}"}) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                self.session = s
                try:
                    yield self
                finally:
                    self.session = None

    async def _call(self, tool: str, args: dict) -> str:
        if tool not in ALLOWED_TOOLS:
            raise PermissionError(f"tool {tool} is not allowed")
        if tool == "execute_junos_command" and not args.get("command", "").lstrip().startswith("show "):
            raise PermissionError("only show commands are allowed")
        res = await self.session.call_tool(tool, args)
        text = "\n".join(c.text for c in res.content if hasattr(c, "text"))
        if res.isError:
            raise RuntimeError(text[:300])
        return text

    async def config(self, device: str) -> list[str]:
        text = await self._call("get_junos_config", {"router_name": device})
        lines = [l.rstrip() for l in text.splitlines() if l.startswith("set ")]
        if not lines:
            raise RuntimeError(f"no set-format configuration returned: {text[:200]}")
        return lines

    async def commits(self, device: str) -> str:
        return await self._call("execute_junos_command",
                                {"router_name": device, "command": "show system commit", "timeout": 60})

    async def facts(self, device: str) -> dict:
        text = await self._call("gather_device_facts", {"router_name": device, "timeout": 60})
        try:
            return json.loads(text[text.index("{"):])
        except Exception:
            return {}
