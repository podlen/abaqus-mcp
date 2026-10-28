"""FastMCP stdio server exposing the seven tools."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import config
from .service import Service
from .transport import SshTransport


def build(svc: Service) -> FastMCP:
    mcp = FastMCP("abaqus-mcp")
    mcp.tool()(svc.license_check)
    mcp.tool()(svc.run_script)
    mcp.tool()(svc.submit_job)
    mcp.tool()(svc.job_status)
    mcp.tool()(svc.odb_query)
    mcp.tool()(svc.model_info)
    mcp.tool()(svc.viewport_png)
    return mcp


def main() -> None:
    cfg = config.load()
    build(Service(cfg, SshTransport(cfg.ssh_host, cfg.max_output))).run()


if __name__ == "__main__":
    main()
