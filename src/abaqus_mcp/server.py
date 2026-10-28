"""FastMCP stdio server exposing the eleven tools."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import config
from .service import Service
from .transport import SshTransport


def build(svc: Service) -> FastMCP:
    mcp = FastMCP("abaqus-mcp")
    mcp.tool()(svc.set_project)
    mcp.tool()(svc.license_check)
    mcp.tool()(svc.run_script)
    mcp.tool()(svc.submit_job)
    mcp.tool()(svc.job_status)
    mcp.tool()(svc.odb_query)
    mcp.tool()(svc.odb_history)
    mcp.tool()(svc.model_summary)
    mcp.tool()(svc.model_views)
    mcp.tool()(svc.viewport_png)
    mcp.tool()(svc.cae_live)
    return mcp


def main() -> None:
    cfg = config.load()
    build(Service(cfg, SshTransport(cfg.ssh_host, cfg.max_output, cfg.ssh_config))).run()


if __name__ == "__main__":
    main()
