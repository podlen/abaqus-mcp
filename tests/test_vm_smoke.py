"""Smoke tests against the live VM with the real ssh/scp transport. No Abaqus needed.

Run with ABAQUS_VM=1 (VM up, config.local.toml filled in): ABAQUS_VM=1 uv run pytest -m vm
"""
import os
import time

import pytest

from abaqus_mcp.config import Config, load
from abaqus_mcp.service import UNREACHABLE, Service
from abaqus_mcp.transport import SshTransport
from conftest import closed_port

pytestmark = [pytest.mark.vm,
              pytest.mark.skipif(os.environ.get("ABAQUS_VM") != "1", reason="set ABAQUS_VM=1 (needs the VM)")]


@pytest.fixture
def svc(tmp_path):
    cfg = load()
    cfg.work_host = tmp_path / "work"
    return Service(cfg, SshTransport(cfg.ssh_host, cfg.max_output))


def test_scp_round_trip(svc, tmp_path):
    t = svc.t
    r = t.run("New-Item -ItemType Directory -Force -Path 'C:\\abaqus-work\\smoke' | Out-Null")
    assert r.returncode == 0, r.stderr
    data = bytes(range(256)) * 40 + b"\r\n\x00end"
    src, dst = tmp_path / "up.bin", tmp_path / "down.bin"
    src.write_bytes(data)
    t.put(src, "C:\\abaqus-work\\smoke\\up.bin")
    t.get("C:\\abaqus-work\\smoke\\up.bin", dst)
    assert dst.read_bytes() == data


def test_license_check_brings_vpn_up(svc):
    import subprocess
    was_up = svc._probe(svc.cfg.probe_timeout)
    try:
        r = svc.license_check()
        assert r["status"] == "ok", r
    finally:
        if not was_up:  # tear down only what this test brought up
            subprocess.run([svc.cfg.vpn_cmd, "down"], capture_output=True, timeout=30)


def test_license_check_closed_port_fast(svc):
    svc.cfg.license_host, svc.cfg.license_port = "127.0.0.1", closed_port()
    t0 = time.monotonic()
    r = svc.license_check()
    assert r["error"] == UNREACHABLE and time.monotonic() - t0 < 30


def test_run_script_without_abaqus(svc, tmp_path):
    s = tmp_path / "noop.py"
    s.write_text("print('hi')\n")
    r = svc.run_script("smoke", str(s))
    assert r["status"] == "error", r
    assert r["exit_code"] == 127 and "abaqus not found" in r["stderr"] and not r["timed_out"]


def test_win32_process_survives_ssh_disconnect(svc):
    """A Win32_Process-launched child outlives the ssh session (Start-Process children do not)."""
    r = svc.t.run("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
                  "@{CommandLine='ping -n 30 127.0.0.1'; CurrentDirectory='C:\\'}; $r.ProcessId")
    assert r.returncode == 0, r.stderr
    pid = int(r.stdout.strip().splitlines()[-1])
    time.sleep(3)  # the creating ssh session is closed by now
    try:
        alive = svc.t.run(f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ 'alive' }}")
        assert "alive" in alive.stdout
    finally:
        svc.t.run(f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue; exit 0")
