"""Load config.local.toml (license_host, license_port, ssh_host, work dirs)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    license_host: str
    license_port: int = 4085
    ssh_host: str = "abaqus-vm"
    work_host: Path = Path.home() / "abaqus-work"
    work_vm: str = "C:\\abaqus-work"
    vpn_cmd: str = str(REPO / "bin" / "abaqus-vpn")
    probe_timeout: float = 4.0
    vpn_timeout: float = 15.0
    ssh_timeout: int = 30
    script_timeout: int = 900
    job_timeout: int = 3600
    max_output: int = 20000


def load(path: str | Path | None = None) -> Config:
    p = Path(path or os.environ.get("ABAQUS_MCP_CONFIG") or REPO / "config.local.toml")
    data = tomllib.loads(p.read_text())
    if "work_host" in data:
        data["work_host"] = Path(data["work_host"]).expanduser()
    return Config(**data)
