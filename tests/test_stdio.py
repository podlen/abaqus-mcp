import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

NAMES = {"license_check", "run_script", "submit_job", "job_status", "odb_query", "model_info", "viewport_png"}


def test_tools_list_over_stdio(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('license_host = "127.0.0.1"\nlicense_port = 1\nssh_host = "none"\n')

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "abaqus_mcp.server"],
                                       env={"ABAQUS_MCP_CONFIG": str(cfg)})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return {t.name for t in (await s.list_tools()).tools}

    assert asyncio.run(asyncio.wait_for(go(), 30)) == NAMES
