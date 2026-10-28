"""Parse Abaqus .sta and .msg text. Status strings and last-increment regex adapted from
MOBAI547800/abaqus-mcp-server log_parser.py (MIT), see NOTICE."""
from __future__ import annotations

import re

_INC = re.compile(r"^\s*(\d+)\s+(\d+)\s+\d+\s+\d+\s+\d+\s+\d+\s+([0-9.E+-]+)\s+([0-9.E+-]+)", re.MULTILINE)
_ERR = re.compile(r"\*{3}\s*ERROR", re.IGNORECASE)
_WARN = re.compile(r"\*{3}\s*WARNING", re.IGNORECASE)


def parse_sta(text: str) -> dict:
    if "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" in text:
        status = "completed"
    elif "THE ANALYSIS HAS NOT BEEN COMPLETED" in text:
        status = "failed"
    elif "THE ANALYSIS HAS BEEN TERMINATED" in text:
        status = "aborted"
    elif text.strip():
        status = "running"
    else:
        status = "unknown"
    out: dict = {"status": status}
    m = list(_INC.finditer(text))
    if m:
        s, i, tt, st = m[-1].groups()  # columns: ... TOTAL ITERS, TOTAL TIME/LPF, STEP TIME/LPF
        out.update(step=int(s), increment=int(i), step_time=float(st), total_time=float(tt))
    return out


def parse_msg(text: str, limit: int = 20) -> dict:
    """ERROR and WARNING blocks: the marker line plus its indented continuation lines."""
    lines = text.splitlines()
    found: dict[str, list[str]] = {"errors": [], "warnings": []}
    i = 0
    while i < len(lines):
        key = "errors" if _ERR.search(lines[i]) else "warnings" if _WARN.search(lines[i]) else None
        if key:
            block = [lines[i].strip()]
            while i + 1 < len(lines) and lines[i + 1].startswith(" ") and lines[i + 1].strip() and "***" not in lines[i + 1]:
                i += 1
                block.append(lines[i].strip())
            found[key].append(" ".join(block)[:500])
        i += 1
    return {k: v[:limit] for k, v in found.items()} | {"n_errors": len(found["errors"]), "n_warnings": len(found["warnings"])}
