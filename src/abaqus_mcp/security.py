"""Name and path validation. Adapted from MOBAI547800/abaqus-mcp-server (MIT), see NOTICE.

Names that reach the VM command line are restricted to a safe character set, so no
shell string can be injected. Host files are resolved and must exist.
"""
from __future__ import annotations

import re
from pathlib import Path

_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
_FILE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,100}")


class SecurityError(ValueError):
    pass


def validate_name(name: str) -> str:
    """Job / model / set name: letters, digits, '_' and '-' only (no dot, see printToFile)."""
    if not _NAME.fullmatch(name or ""):
        raise SecurityError(f"invalid name {name!r}: use letters, digits, _ and - (max 64)")
    return name


def validate_filename(name: str) -> str:
    """Plain file name without directory part or '..'."""
    if not _FILE.fullmatch(name or "") or ".." in name:
        raise SecurityError(f"invalid file name {name!r}")
    return name


def validate_host_file(path: str | Path) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise SecurityError(f"file not found on host: {path}")
    validate_filename(p.name)
    return p


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return f"{text[:half]}\n... [truncated {len(text) - max_chars} chars] ...\n{text[-half:]}"
