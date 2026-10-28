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


# -- convergence detail (C5) -------------------------------------------------------------
# .sta row = one attempt: STEP INC ATT SEVERE EQUIL TOTAL-ITERS TOTAL-TIME STEP-TIME INC-OF-TIME.
# A cut-back is a row whose ATT field ends in U; increments done are rows without U.
_ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)(U?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(\S+)", re.MULTILINE)
_STEP_HDR = re.compile(r"^\s*STEP\s+(\d+)\s+INCREMENT\s+(\d+)")
_INC_START = re.compile(r"^\s*INCREMENT\s+(\d+)\s+STARTS")
_NUM = re.compile(r"[-+]?\d+(\.\d*)?([eE][-+]?\d+)?")
WARN_TYPES = [  # (name, regex on the first line of the warning), first match wins
    ("negative eigenvalues", re.compile(r"NEGATIVE EIGENVALUE", re.I)),
    ("contact overclosure", re.compile(r"OVERCLOSURE", re.I)),
    ("contact chatter", re.compile(r"CHATTER", re.I)),
    ("excessive distortion", re.compile(r"DISTORT", re.I)),
    ("plasticity strain increment", re.compile(r"STRAIN INCREMENT HAS EXCEEDED", re.I)),
]


def _f(s: str) -> float:
    return float(s.replace("D", "E"))


def sta_convergence(text: str) -> dict:
    """Per-step convergence numbers from the .sta table."""
    steps: dict[int, list] = {}
    for m in _ROW.finditer(text):
        steps.setdefault(int(m[1]), []).append(m)
    out = {}
    for s, rows in steps.items():
        done = [r for r in rows if not r[4]]
        eq = [int(r[6]) for r in rows]
        d = {"increments_done": len(done), "attempts": len(rows), "cutbacks": len(rows) - len(done),
             "equil_iters_max": max(eq), "equil_iters_mean": round(sum(eq) / len(eq), 2),
             "severe_iters": sum(int(r[5]) for r in rows)}
        if done:
            incs = [_f(r[10]) for r in done]
            d.update(min_increment=min(incs), last_increment=incs[-1], step_time=_f(done[-1][9]))
        out[str(s)] = d
    return out


def msg_warning_groups(text: str, max_groups: int = 12) -> list[dict]:
    """Warnings grouped by type (WARN_TYPES) or, for other warnings, by first line with numbers removed.
    first = step and increment of the last 'INCREMENT n STARTS' above the first occurrence."""
    groups: dict[str, dict] = {}
    step = inc = 0
    for line in text.splitlines():
        if (m := _STEP_HDR.match(line)):
            step, inc = int(m[1]), int(m[2])
        elif (m := _INC_START.match(line)):
            inc = int(m[1])
        elif (m := re.search(r"\*{3}\s*WARNING:?\s*(.*)", line, re.I)):
            first = m[1].strip()
            name = next((n for n, rx in WARN_TYPES if rx.search(first)), None)
            if name is None:
                name = " ".join(_NUM.sub("", first).split())
            g = groups.setdefault(name, {"warning": name, "count": 0, "first_step": step, "first_increment": inc})
            g["count"] += 1
    return sorted(groups.values(), key=lambda g: -g["count"])[:max_groups]


def last_errors(text: str, n: int = 5) -> list[str]:
    return parse_msg(text, limit=10**6)["errors"][-n:]
