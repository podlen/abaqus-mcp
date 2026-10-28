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
    r = svc.license_check()
    assert r["status"] == "ok", r


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
