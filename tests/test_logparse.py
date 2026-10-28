from abaqus_mcp.logparse import parse_msg, parse_sta
from abaqus_mcp.security import SecurityError, validate_filename, validate_name
import pytest
from conftest import FIX


def test_sta_states():
    assert parse_sta((FIX / "ok.sta").read_text())["status"] == "completed"
    assert parse_sta((FIX / "failed.sta").read_text())["status"] == "failed"
    r = parse_sta((FIX / "running.sta").read_text())
    assert (r["status"], r["step"], r["increment"], r["total_time"]) == ("running", 1, 2, 0.3)
    assert parse_sta("")["status"] == "unknown"


def test_msg_errors():
    m = parse_msg((FIX / "nobc.msg").read_text())
    # excerpt of a real Abaqus/Standard 2026 run without BCs: the singularity is a warning
    assert m["n_errors"] == 1 and "TOO MANY ATTEMPTS" in m["errors"][0]
    assert m["n_warnings"] == 2 and "NUMERICAL SINGULARITY" in m["warnings"][0]
    assert parse_msg((FIX / "ok.msg").read_text())["n_errors"] == 0


def test_security():
    assert validate_name("cant-1_a") == "cant-1_a"
    for bad in ("a b", "a;b", "a.b", "..", "", "a&b", "x" * 65):
        with pytest.raises(SecurityError):
            validate_name(bad)
    assert validate_filename("m.inp") == "m.inp"
    for bad in ("../m.inp", "a/b.inp", "a\\b", "a;b.py", ".hidden"):
        with pytest.raises(SecurityError):
            validate_filename(bad)
