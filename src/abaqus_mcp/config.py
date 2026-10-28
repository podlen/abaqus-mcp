"""Load config.local.toml. Defaults live here once; setup.sh and bin/ read them with
`python -m abaqus_mcp.config --print`."""
from __future__ import annotations

import os
import shlex
import sys
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# keys that setup.sh and bin/ need, printed as KEY=value (upper case)
SHELL_KEYS = ("vm_name", "ram_mb", "vcpus", "disk_gb", "ssh_port", "rdp_port", "state_dir", "iso_dir",
              "vpn_connection", "license_host", "license_port", "ssh_host")


@dataclass
class Config:
    license_host: str = ""
    license_port: int = 4085
    vm_name: str = "abaqus-mcp"
    ram_mb: int = 8192
    vcpus: int = 6
    disk_gb: int = 80
    ssh_port: int = 2222
    rdp_port: int = 3390
    state_dir: Path = Path.home() / ".local" / "share" / "abaqus-mcp"
    iso_dir: Path | None = None  # optional: reuse win11-eval.iso and virtio-win.iso found here
    vpn_connection: str = "fs-abaqus"
    ssh_host: str = "abaqus-vm"  # Host alias inside <state_dir>/ssh_config
    work_vm: str = "C:\\abaqus-work"
    abaqus_cmd: str = "C:\\Program Files\\SIMULIA\\Commands\\abaqus.bat"
    vpn_cmd: str = str(REPO / "bin" / "abaqus-vpn")
    probe_timeout: float = 4.0
    vpn_timeout: float = 15.0
    ssh_timeout: int = 30
    script_timeout: int = 900
    job_timeout: int = 3600
    max_output: int = 20000
    live_probe_timeout: float = 4.0  # SSH heartbeat probe; keeps "no live CAE session" under 5 s
    live_stale_s: float = 3.0

    @property
    def ssh_config(self) -> Path:
        return Path(self.state_dir) / "ssh_config"


def load(path: str | Path | None = None) -> Config:
    p = Path(path or os.environ.get("ABAQUS_MCP_CONFIG") or REPO / "config.local.toml")
    data = tomllib.loads(p.read_text()) if p.exists() else {}
    data.pop("work_host", None)  # removed: the project directory replaces it
    for k in ("state_dir", "iso_dir"):
        if data.get(k):
            data[k] = Path(data[k]).expanduser()
        else:
            data.pop(k, None)
    return Config(**data)


def shell_lines(cfg: Config) -> str:
    vals = {f.name: getattr(cfg, f.name) for f in fields(cfg) if f.name in SHELL_KEYS}
    return "".join(f"{k.upper()}={shlex.quote('' if vals[k] is None else str(vals[k]))}\n" for k in SHELL_KEYS)


if __name__ == "__main__":
    if sys.argv[1:] != ["--print"]:
        sys.exit("usage: python -m abaqus_mcp.config --print")
    sys.stdout.write(shell_lines(load()))
