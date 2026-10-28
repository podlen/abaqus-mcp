"""Transports: SSH and SCP to the VM, or the local Windows machine. Subprocess pattern (timeout, kill, bounded output)
adapted from MOBAI547800/abaqus-mcp-server abaqus_cli.py (MIT), see NOTICE.

Arguments are lists, never a shell string on the host. The command string for the VM
(PowerShell 5.1) is built only from validated names and single-quoted literals.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .security import truncate

_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed: float
    timed_out: bool = False


class TransportError(RuntimeError):
    pass


class SshTransport:
    def __init__(self, ssh_host: str, max_output: int = 20000, ssh_config: Path | str | None = None) -> None:
        self.host = ssh_host
        self.F = ["-F", str(ssh_config)] if ssh_config else []
        self.max_output = max_output

    def _exec(self, argv: list[str], timeout: float) -> RunResult:
        t0 = time.monotonic()
        try:
            p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", errors="replace",
                               timeout=timeout)
        except subprocess.TimeoutExpired as e:  # subprocess.run kills the child on expiry
            out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            err = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
            return RunResult(-1, truncate(out, self.max_output), truncate(err, self.max_output),
                             time.monotonic() - t0, timed_out=True)
        return RunResult(p.returncode, truncate(p.stdout, self.max_output),
                         truncate(p.stderr, self.max_output), time.monotonic() - t0)

    def run(self, command: str, timeout: float = 60) -> RunResult:
        """Run a PowerShell command line on the VM."""
        return self._exec(["ssh", *self.F, *_SSH_OPTS, self.host, command], timeout)

    def put(self, local: Path, remote: str, timeout: float = 120) -> None:
        r = self._exec(["scp", "-q", *self.F, *_SSH_OPTS, str(local), f"{self.host}:{remote.replace(chr(92), '/')}"], timeout)
        if r.returncode != 0:
            raise TransportError(f"SCP upload failed: {r.stderr.strip()}")

    def get(self, remote: str, local: Path, timeout: float = 120) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        r = self._exec(["scp", "-q", *self.F, *_SSH_OPTS, f"{self.host}:{remote.replace(chr(92), '/')}", str(local)], timeout)
        if r.returncode != 0:
            raise TransportError(f"SCP download failed: {r.stderr.strip()}")


class LocalTransport:
    """Native Windows: the same PowerShell command lines run in a local Windows PowerShell 5.1,
    files are copied on the local disk. The command goes in as -EncodedCommand (UTF-16LE base64),
    so no host-side quoting applies; output is read as UTF-8."""

    _PREFIX = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'; "

    def __init__(self, max_output: int = 20000) -> None:
        self.max_output = max_output

    def _exec(self, argv: list[str], timeout: float) -> RunResult:
        """As SshTransport._exec, but a timeout ends the whole process tree: on Windows subprocess.run
        kills only powershell.exe and then waits for the pipes, which abaqus.bat and its children hold."""
        t0 = time.monotonic()
        with subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              encoding="utf-8", errors="replace") as p:
            try:
                out, err = p.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
                try:
                    out, err = p.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    out, err = "", ""
                return RunResult(-1, truncate(out, self.max_output), truncate(err, self.max_output),
                                 time.monotonic() - t0, timed_out=True)
        return RunResult(p.returncode, truncate(out, self.max_output), truncate(err, self.max_output),
                         time.monotonic() - t0)

    def run(self, command: str, timeout: float = 60) -> RunResult:
        enc = base64.b64encode((self._PREFIX + command).encode("utf-16-le")).decode()
        return self._exec(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
                           "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc], timeout)

    def _copy(self, src: Path | str, dst: Path | str, what: str) -> None:
        try:
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        except OSError as e:
            raise TransportError(f"{what} failed: {e}") from e

    def put(self, local: Path, remote: str, timeout: float = 120) -> None:
        self._copy(local, remote, "copy to the work folder")

    def get(self, remote: str, local: Path, timeout: float = 120) -> None:
        self._copy(remote, local, "copy from the work folder")


def make(cfg) -> SshTransport | LocalTransport:
    """Transport named by cfg.transport."""
    if cfg.transport == "local":
        return LocalTransport(cfg.max_output)
    if cfg.transport == "ssh":
        return SshTransport(cfg.ssh_host, cfg.max_output, cfg.ssh_config)
    raise ValueError(f"transport must be 'local' or 'ssh', not {cfg.transport!r}")
