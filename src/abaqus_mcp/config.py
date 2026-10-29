"""Load config.local.toml. Defaults live here once; setup.sh and bin/ read them with
`python -m abaqus_mcp.config --print`."""
from __future__ import annotations

import os
import re
import shlex
import shutil
import sys
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WINDOWS = os.name == "nt"
DSLICSRV = Path(r"C:\ProgramData\DassaultSystemes\Licenses\DSLicSrv.txt")
_ABAQUS_BAT = (r"C:\Program Files\SIMULIA\Commands\abaqus.bat", r"C:\SIMULIA\Commands\abaqus.bat")

# keys that setup.sh and bin/ need, printed as KEY=value (upper case)
SHELL_KEYS = ("vm_name", "ram_mb", "vcpus", "disk_gb", "ssh_port", "rdp_port", "state_dir", "iso_dir",
              "vpn_connection", "license_host", "license_port", "ssh_host")


def _state_dir() -> Path:
    if WINDOWS and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "abaqus-mcp"
    return Path.home() / ".local" / "share" / "abaqus-mcp"


def find_abaqus() -> str:
    """Native Windows: `abaqus` on PATH, else the first existing launcher of a default install."""
    found = shutil.which("abaqus")
    if found:
        return found
    return next((p for p in _ABAQUS_BAT if Path(p).is_file()), _ABAQUS_BAT[0])


def dslicsrv_host(path: Path | None = None) -> tuple[str, int] | None:
    """First `host:port` line of the DSLS client file written by the Abaqus installer."""
    try:
        text = (path or DSLICSRV).read_text(errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        m = re.fullmatch(r"\s*([A-Za-z0-9_.-]+):(\d+)\s*", line)
        if m:
            return m[1], int(m[2])
    return None


@dataclass
class Config:
    transport: str = "local" if WINDOWS else "ssh"  # local: this Windows machine; ssh: the VM
    license_host: str = ""
    license_port: int = 4085
    vm_name: str = "abaqus-mcp"
    ram_mb: int = 8192
    vcpus: int = 6
    disk_gb: int = 80
    ssh_port: int = 2222
    rdp_port: int = 3390
    state_dir: Path = _state_dir()
    iso_dir: Path | None = None  # optional: reuse win11-eval.iso and virtio-win.iso found here
    vpn_connection: str = "fs-abaqus"
    ssh_host: str = "abaqus-vm"  # Host alias inside <state_dir>/ssh_config
    work_vm: str = "C:\\abaqus-work"
    abaqus_cmd: str = "C:\\Program Files\\SIMULIA\\Commands\\abaqus.bat"
    vpn_cmd: str = "" if WINDOWS else str(REPO / "bin" / "abaqus-vpn")  # empty: never start a VPN
    probe_timeout: float = 4.0
    vpn_timeout: float = 15.0
    ssh_timeout: int = 30
    script_timeout: int = 900
    job_timeout: int = 3600
    max_output: int = 20000
    print_cap: int = 4000  # run_script: characters kept of print_output, stdout and stderr
    node_limit: int = 0  # model_summary warns above this many nodes; 0: off (Teaching Edition: 250000)
    live_probe_timeout: float = 4.0  # SSH heartbeat probe; keeps "no live CAE session" under 5 s
    live_stale_s: float = 3.0

    @property
    def ssh_config(self) -> Path:
        return Path(self.state_dir) / "ssh_config"


def load(path: str | Path | None = None) -> Config:
    p = Path(path or os.environ.get("ABAQUS_MCP_CONFIG") or REPO / "config.local.toml")
    try:  # utf-8-sig: older Notepad saves UTF-8 with a byte-order mark
        data = tomllib.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{p}: {e}\nfix: text values need quotes; put Windows paths in single quotes, "
                         "e.g. abaqus_cmd = 'C:\\SIMULIA\\Commands\\abaqus.bat'")
    if unknown := sorted(set(data) - {f.name for f in fields(Config)} - {"work_host"}):
        raise SystemExit(f"{p}: unknown setting(s) {', '.join(unknown)}\nfix: check the spelling against the "
                         "settings table in README.md")
    data.pop("work_host", None)  # removed: the project directory replaces it
    for k in ("state_dir", "iso_dir"):
        if data.get(k):
            data[k] = Path(data[k]).expanduser()
        else:
            data.pop(k, None)
    if WINDOWS and data.get("transport", "local") == "local":
        data.setdefault("abaqus_cmd", find_abaqus())
        if not data.get("license_host") and (hp := dslicsrv_host()):
            data["license_host"] = hp[0]
            data.setdefault("license_port", hp[1])
    return Config(**data)


def shell_lines(cfg: Config) -> str:
    vals = {f.name: getattr(cfg, f.name) for f in fields(cfg) if f.name in SHELL_KEYS}
    return "".join(f"{k.upper()}={shlex.quote('' if vals[k] is None else str(vals[k]))}\n" for k in SHELL_KEYS)


if __name__ == "__main__":
    if sys.argv[1:] == ["--print"]:
        sys.stdout.write(shell_lines(load()))
    elif sys.argv[1:] == ["--json"]:  # read by setup-windows.ps1
        import json
        c = load()
        print(json.dumps({f.name: str(v) if isinstance(v := getattr(c, f.name), Path) else v for f in fields(c)}))
    else:
        sys.exit("usage: python -m abaqus_mcp.config --print | --json")
