"""Native Windows mode (spec 004): config defaults, licence host lookup, local transport.
The PowerShell half runs only on Windows."""
import os
import sys
from pathlib import Path

import pytest

from abaqus_mcp import config, transport
from abaqus_mcp.config import Config
from conftest import closed_port

PLUG = Path(__file__).parents[1] / "vm" / "plugin"
windows = pytest.mark.skipif(os.name != "nt", reason="needs Windows PowerShell")

DSLIC = "# DSLS client configuration\n\n  lic.example.org:4085  \nother.example.org:4086\n"


def test_dslicsrv_first_host_port_line(tmp_path):
    f = tmp_path / "DSLicSrv.txt"
    f.write_text(DSLIC)
    assert config.dslicsrv_host(f) == ("lic.example.org", 4085)
    f.write_text("# only a comment\n")
    assert config.dslicsrv_host(f) is None
    assert config.dslicsrv_host(tmp_path / "missing.txt") is None


def test_find_abaqus_branches(monkeypatch, tmp_path):
    monkeypatch.setattr(config.shutil, "which", lambda n: r"D:\SIMULIA\Commands\abaqus.BAT")
    assert config.find_abaqus() == r"D:\SIMULIA\Commands\abaqus.BAT"
    monkeypatch.setattr(config.shutil, "which", lambda n: None)
    second = tmp_path / "abaqus.bat"
    second.write_text("")
    monkeypatch.setattr(config, "_ABAQUS_BAT", (str(tmp_path / "none.bat"), str(second)))
    assert config.find_abaqus() == str(second)
    second.unlink()
    assert config.find_abaqus() == str(tmp_path / "none.bat")  # nothing found: the first default


def test_load_on_windows(monkeypatch, tmp_path):
    lic = tmp_path / "DSLicSrv.txt"
    lic.write_text(DSLIC)
    monkeypatch.setattr(config, "WINDOWS", True)
    monkeypatch.setattr(config, "DSLICSRV", lic)
    monkeypatch.setattr(config, "find_abaqus", lambda: r"C:\X\abaqus.bat")
    cfg = tmp_path / "c.toml"
    cfg.write_text('transport = "local"\nvpn_cmd = ""\n')
    c = config.load(cfg)
    assert (c.abaqus_cmd, c.license_host, c.license_port) == (r"C:\X\abaqus.bat", "lic.example.org", 4085)
    cfg.write_text('transport = "local"\nlicense_host = "mine"\nabaqus_cmd = "C:\\\\A\\\\abq.bat"\n')
    c = config.load(cfg)
    assert (c.abaqus_cmd, c.license_host, c.license_port) == (r"C:\A\abq.bat", "mine", 4085)
    cfg.write_text('transport = "ssh"\n')  # the VM keeps its own defaults
    c = config.load(cfg)
    assert c.license_host == "" and c.abaqus_cmd == Config.abaqus_cmd


def test_transport_choice():
    assert isinstance(transport.make(Config(transport="local")), transport.LocalTransport)
    assert isinstance(transport.make(Config(transport="ssh")), transport.SshTransport)
    with pytest.raises(ValueError):
        transport.make(Config(transport="wsl"))


def test_local_put_get(tmp_path):
    t = transport.LocalTransport()
    src = tmp_path / "a.inp"
    src.write_text("*HEADING\n")
    t.put(src, str(tmp_path / "work" / "job" / "a.inp"))
    t.get(str(tmp_path / "work" / "job" / "a.inp"), tmp_path / "back" / "a.inp")
    assert (tmp_path / "back" / "a.inp").read_text() == "*HEADING\n"
    with pytest.raises(transport.TransportError):
        t.get(str(tmp_path / "work" / "missing.json"), tmp_path / "x.json")


def test_license_not_checked_without_host(make):
    svc, t = make(license_host="")
    r = svc.license_check()
    assert r["status"] == "ok" and r["license"] == "not checked"


def test_license_no_vpn_cmd_asks_for_vpn(make, monkeypatch):
    svc, _ = make(port=closed_port(), vpn_cmd="")
    ran = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: ran.append(a))
    r = svc.license_check()
    assert r["status"] == "error" and "connect the university VPN" in r["hint"] and not ran


def test_live_dir_file(tmp_path, monkeypatch):
    for f in ("mcp_live_core.py",):
        (tmp_path / f).write_text((PLUG / f).read_text())
    (tmp_path / "live_dir.txt").write_text("D:\\work\\live\n")
    monkeypatch.delenv("ABAQUS_MCP_LIVE_DIR", raising=False)
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("mcp_live_core", None)
    import mcp_live_core
    try:
        assert mcp_live_core.LIVE_DIR == "D:\\work\\live"
    finally:
        sys.modules.pop("mcp_live_core", None)


@windows
def test_local_run_powershell_quoting_and_utf8():
    t = transport.LocalTransport()
    r = t.run("$a='it''s \"quoted\"'; Write-Output $a; Write-Output 'Ž č'; exit 3")
    assert r.returncode == 3
    assert r.stdout.splitlines() == ["it's \"quoted\"", "Ž č"]


def test_exec_child_gets_empty_stdin():
    # the MCP server's stdin is the JSON-RPC pipe: a child that inherited it hung `abaqus cae noGUI`
    r = transport.LocalTransport()._exec([sys.executable, "-c", "import sys; print(len(sys.stdin.read()))"], 20)
    assert not r.timed_out and r.stdout.strip() == "0"


def test_config_errors_are_one_line_with_fix(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text("abaqus_cmd = C:\\nope\\abaqus.bat\n")
    with pytest.raises(SystemExit, match="single quotes"):
        config.load(cfg)
    cfg.write_text("abaqus_command = 'x'\n")
    with pytest.raises(SystemExit, match="unknown setting.*abaqus_command"):
        config.load(cfg)
    cfg.write_bytes(b"\xef\xbb\xbflicense_port = 27000\n")  # Notepad's UTF-8 with BOM
    assert config.load(cfg).license_port == 27000


@windows
def test_local_timeout_ends_the_child_tree():
    t = transport.LocalTransport()
    r = t.run("cmd /c ping -n 60 127.0.0.1", timeout=3)  # ping inherits the output pipes, as abaqus.bat does
    assert r.timed_out and r.elapsed < 20
    assert "ping" not in t.run("Get-Process ping -ErrorAction SilentlyContinue | ForEach-Object Name").stdout


@windows
def test_local_number_output_ignores_culture():
    r = transport.LocalTransport().run('[Threading.Thread]::CurrentThread.CurrentCulture="sl-SI"; "$([math]::Round(0.53,2))"')
    assert r.stdout.strip() == "0.53"
