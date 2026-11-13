import asyncio, json
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
TOKEN=open("/secrets/jmcp-backend.token").read().strip()
async def main():
    async with streamablehttp_client("http://127.0.0.1:30030/mcp/",headers={"Authorization":f"Bearer {TOKEN}"}) as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()
            for t in (await s.list_tools()).tools:
                if t.name in ("get_junos_config","execute_junos_command","gather_device_facts","execute_junos_command_batch"):
                    print(t.name, json.dumps(t.inputSchema.get("properties",{}))[:400])
            r=await s.call_tool("get_junos_config",{"router_name":"qfx1"})
            print("CFG HEAD:", "\n".join(c.text for c in r.content)[:300])
asyncio.run(main())
