import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
TOKEN=open("/secrets/jmcp-backend.token").read().strip()
def txt(r): return "\n".join(c.text for c in r.content if hasattr(c,"text"))
async def main():
    async with streamablehttp_client("http://127.0.0.1:30030/mcp/",headers={"Authorization":f"Bearer {TOKEN}"}) as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()
            for d in ("qfx1","qfx2"):
                f=txt(await s.call_tool("execute_junos_command",{"router_name":d,"command":"show version | match \"Hostname|Model|Junos:\""}))
                c=txt(await s.call_tool("get_junos_config",{"router_name":d}))
                print(d,"|"," ".join(f.split()),"| config lines:",len(c.splitlines()))
                print("  RO:",txt(await s.call_tool("execute_junos_command",{"router_name":d,"command":"request system reboot"}))[:60])
asyncio.run(main())
