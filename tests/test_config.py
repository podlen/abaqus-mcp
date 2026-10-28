import os
import subprocess
from pathlib import Path

import pytest

from abaqus_mcp import config

REPO = Path(__file__).parents[1]
# shell lines, VM defaults and setup.sh belong to the Linux host
pytestmark = pytest.mark.skipif(os.name == "nt", reason="Linux VM host only")


def test_print_non_default_values(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('vm_name = "w1"\nram_mb = 4096\nvcpus = 2\ndisk_gb = 60\nssh_port = 2200\nrdp_port = 3400\n'
                   f'state_dir = "{tmp_path}/st ate"\niso_dir = "{tmp_path}/iso"\nvpn_connection = "my vpn"\n'
                   'license_host = "10.0.0.5"\nlicense_port = 27000\nssh_host = "h"\n')
    r = subprocess.run(["uv", "run", "--directory", str(REPO), "python", "-m", "abaqus_mcp.config", "--print"],
                       capture_output=True, text=True, env={**os.environ, "ABAQUS_MCP_CONFIG": str(cfg)})
    assert r.returncode == 0, r.stderr
    assert r.stdout == (f"VM_NAME=w1\nRAM_MB=4096\nVCPUS=2\nDISK_GB=60\nSSH_PORT=2200\nRDP_PORT=3400\n"
                        f"STATE_DIR='{tmp_path}/st ate'\nISO_DIR={tmp_path}/iso\nVPN_CONNECTION='my vpn'\n"
                        "LICENSE_HOST=10.0.0.5\nLICENSE_PORT=27000\nSSH_HOST=h\n")


def test_old_config_still_loads(tmp_path):
    p = tmp_path / "old.toml"
    p.write_text('license_host = "h"\nlicense_port = 1\nssh_host = "abaqus-vm"\nwork_host = "~/abaqus-work"\n')
    c = config.load(p)
    assert (c.vm_name, c.ssh_port, c.vpn_connection) == ("abaqus-mcp", 2222, "fs-abaqus")
    assert c.state_dir == Path.home() / ".local/share/abaqus-mcp" and c.iso_dir is None
    assert c.ssh_config == c.state_dir / "ssh_config"


def uninstall(cfg_path):
    return subprocess.run([str(REPO / "setup.sh"), "uninstall"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          env={**os.environ, "ABAQUS_MCP_CONFIG": str(cfg_path)})


def test_uninstall_refuses_home_and_unmarked_dir(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('state_dir = "~"\n')
    r = uninstall(cfg)
    assert r.returncode != 0 and "refus" in r.stderr
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "keep.txt").write_text("x")
    cfg.write_text(f'state_dir = "{plain}"\n')
    r = uninstall(cfg)
    assert r.returncode != 0 and "marker" in r.stderr and (plain / "keep.txt").exists()
    cfg.write_text(f'state_dir = "{REPO.parent}"\n')  # a parent of the repo, marker or not
    assert uninstall(cfg).returncode != 0
