"""SSH and SCP transport to the VM. Subprocess pattern (timeout, kill, bounded output)
adapted from MOBAI547800/abaqus-mcp-server abaqus_cli.py (MIT), see NOTICE.

Arguments are lists, never a shell string on the host. The command string for the VM
(PowerShell 5.1) is built only from validated names and single-quoted literals.
"""
from __future__ import annotations

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
            p = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=timeout)
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
