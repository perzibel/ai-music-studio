"""End-to-end test of the MCP server over stdio (the way Claude Code / Codex talk to it).

Usage: .venv\\Scripts\\python.exe tools\\mcp_smoke_test.py
"""
import asyncio
import json
import os

from mcp import ClientSession, StdioServerParameters

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=r".venv\Scripts\python.exe", args=["run_server.py"])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])
            res = await s.call_tool("list_instruments", {"search": "guitar"})
            print("GUITARS:", [json.loads(c.text).get("instrument") for c in res.content][:6])
            song = {"title": "mcp hq test", "bpm": 100, "reverb": {"type": "room"}, "tracks": [
                {"name": "Piano", "instrument": "sfz:grand_piano", "sustain": [[0, 3.9]],
                 "notes": [{"chord": "Cmaj7", "oct": 4, "t": 0, "d": 1}]},
                {"name": "Gtr", "instrument": "sfz:electric_guitar", "amp": "rock",
                 "notes": [{"p": "E4", "t": 0, "d": 2, "bend": 2, "vib": 0.2}]},
                {"name": "Drums", "instrument": "sfz:acoustic_drums", "pattern": {"kick": "x...x...", "snare": "..x...x."}}]}
            res = await s.call_tool("render_song", {"song": song})
            out = json.loads(res.content[0].text)
            print("RENDER:", out.get("error") or {k: out[k] for k in ("duration_seconds", "loudness", "warnings")})
            res = await s.call_tool("list_songs", {})
            print("SONGS:", len(res.content))


asyncio.run(main())
