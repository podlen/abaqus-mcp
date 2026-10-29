import atexit
import functools
import shutil
import socket
import tempfile
from pathlib import Path

import pytest

from abaqus_mcp.config import Config
from abaqus_mcp.service import Service
from abaqus_mcp.transport import RunResult

FIX = Path(__file__).parent / "fixtures"


class FakeTransport:
    """Records VM commands; `handler(command) -> RunResult | None` supplies canned output."""

    def __init__(self, handler=None):
        self.handler = handler
        self.commands: list[str] = []
        self.puts: dict[str, str] = {}
        self.gets: list[str] = []
        self.files: dict[str, str] = {}  # remote path -> text served by get
        self.missing: set[str] = set()  # remote paths whose get fails

    def run(self, command, timeout=60):
        self.commands.append(command)
        r = self.handler(command) if self.handler else None
        return r or RunResult(0, "", "", 0.0)

    def put(self, local, remote, timeout=120):
        self.puts[remote] = Path(local).read_text()

    def get(self, remote, local, timeout=120):
        self.gets.append(remote)
        if remote in self.missing:
            from abaqus_mcp.transport import TransportError
            raise TransportError(f"no such file: {remote}")
        Path(local).write_bytes(self.files[remote].encode() if remote in self.files else b"\x89PNG")


def ok(stdout="", stderr="", rc=0):
    return RunResult(rc, stdout, stderr, 0.1)


def closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def listener():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    yield s.getsockname()[1]
    s.close()


@pytest.fixture
def make(tmp_path, listener, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))  # set_project only accepts paths under $HOME
    monkeypatch.setenv("USERPROFILE", str(home))  # Path.home() on Windows

    def _make(handler=None, project=True, **kw):
        cfg = Config(license_host=kw.pop("license_host", "127.0.0.1"), license_port=kw.pop("port", listener),
                     state_dir=tmp_path / "state", **kw)
        t = FakeTransport(handler)
        svc = Service(cfg, t)
        if project:
            assert svc.set_project(str(home / "proj"))["status"] == "ok"
        return svc, t
    return _make


@functools.cache
def e2e_project() -> Path:
    """One project directory under $HOME for the E2E and VM tests; removed at exit."""
    d = Path(tempfile.mkdtemp(prefix="abaqus-mcp-e2e-", dir=Path.home())).resolve()
    atexit.register(shutil.rmtree, d, ignore_errors=True)
    return d
