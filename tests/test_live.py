import json
import sys
import time
from pathlib import Path

import pytest

from conftest import ok

PLUG = Path(__file__).parents[1] / "vm" / "plugin"
sys.path.insert(0, str(PLUG))
import mcp_live_core as core  # noqa: E402
import mcp_live_kernel as kern  # noqa: E402

LIVE = "C:\\abaqus-work\\live"


def live_handler(age="0.5", result=None, timeout=False, notrun=False):
    def h(c):
        if "heartbeat.txt" in c:
            return ok(f"{age}\n" if age is not None else "")
        if "outbox" in c:
            return ok("MCP_LIVE_NOTRUN\n" if notrun else "MCP_LIVE_TIMEOUT\n" if timeout else json.dumps(result or {"ok": True, "output": "hi\n", "result": {"a": 1}, "traceback": ""}))
    return h


def test_cae_live_ok(make):
    svc, t = make(live_handler())
    r = svc.cae_live("print('hi')", timeout=7)
    assert r["status"] == "ok" and r["output"] == "hi\n" and r["result"] == {"a": 1}
    part = next(k for k in t.puts if k.endswith(".part"))
    assert part.startswith(LIVE + "\\inbox\\") and t.puts[part] == "print('hi')"
    cmd = t.commands[-1]
    assert "Move-Item" in cmd and ".py'" in cmd and "AddSeconds(7)" in cmd and "Milliseconds 250" in cmd
    assert not list((svc.cfg.work_host / "_live").glob("*.part"))


@pytest.mark.parametrize("age", [None, "3.5", "junk"])
def test_cae_live_no_session(make, age):
    svc, t = make(live_handler(age=age))
    t0 = time.monotonic()
    r = svc.cae_live("1")
    assert r["status"] == "error" and r["error"] == "no live CAE session"
    assert time.monotonic() - t0 < 5 and t.puts == {}


def test_cae_live_probe_uses_short_timeout(make):
    svc, t = make(live_handler())
    seen = []
    orig = t.run
    t.run = lambda c, timeout=60: (seen.append(timeout), orig(c, timeout))[1]
    svc.cae_live("1", timeout=9)
    assert seen[0] == svc.cfg.live_probe_timeout <= 4.5 and seen[1] >= 9


def test_cae_live_traceback_then_next_call_works(make):
    tb = "Traceback (most recent call last):\n  File x\nValueError: deliberate\n"
    svc, t = make(live_handler(result={"ok": False, "output": "", "traceback": tb, "result": None}))
    r = svc.cae_live("raise ValueError('deliberate')")
    assert r["status"] == "error" and r["error"] == "ValueError: deliberate" and "Traceback" in r["traceback"]
    svc2, _ = make(live_handler())
    assert svc2.cae_live("1")["status"] == "ok"


def test_cae_live_timeout(make):
    svc, _ = make(live_handler(timeout=True))
    r = svc.cae_live("1", timeout=2)
    assert r["status"] == "error" and r["error"] == "timed out while running" and "log id" in r["hint"]


def test_cae_live_timeout_not_run(make):
    svc, t = make(live_handler(notrun=True))
    r = svc.cae_live("1", timeout=2)
    assert r["status"] == "error" and r["error"] == "timed out, not run"
    cmd = t.commands[-1]
    assert "Remove-Item -LiteralPath" in cmd and "inbox" in cmd and "-ErrorAction Stop" in cmd


# -- model_summary / model_views live mode ----------------------------------
def test_model_summary_live(make):
    svc, t = make(live_handler(result={"ok": True, "output": "", "traceback": "", "result": {"source": "live", "model": "M"}}))
    r = svc.model_summary("jb")
    assert r["source"] == "live" and r["status"] == "ok"
    s = next(v for k, v in t.puts.items() if k.endswith(".part"))
    assert "def model_summary(mdb" in s and 'model_summary(mdb, None, "live")' in s
    assert not any("noGUI" in c for c in t.commands)


def test_model_summary_cae_file_or_no_session_stays_noGUI(make, tmp_path):
    svc, t = make(live_handler())
    t.files["C:\\abaqus-work\\jb\\_model_summary.json"] = json.dumps({"source": "jb.cae"})
    assert svc.model_summary("jb", live=False)["source"] == "jb.cae"
    svc, t = make(live_handler(age=None))
    t.files["C:\\abaqus-work\\jb\\_model_summary.json"] = json.dumps({"source": "jb.cae"})
    assert svc.model_summary("jb")["source"] == "jb.cae"


def test_model_views_live(make):
    res = {"files": ["x"], "shown": "assembly", "highlight": "S"}
    svc, t = make(live_handler(result={"ok": True, "output": "", "traceback": "", "result": res}))
    r = svc.model_views("jb", highlight="S")
    assert r["source"] == "live" and set(r["paths"]) == {"iso", "front", "top"}
    assert t.gets == [f"{LIVE}\\views\\jb_views_S_{v}.png" for v in ("iso", "front", "top")]
    s = next(v for k, v in t.puts.items() if k.endswith(".part"))
    assert "def render_views" in s and "_old = _vp.displayedObject" in s


# -- plug-in logic without Abaqus -------------------------------------------
def test_kernel_wrapper_output_traceback_result(tmp_path):
    s, o = tmp_path / "a.py", tmp_path / "a.json"
    s.write_text("print('x')\nresult = {'n': 2}\n")
    kern.run(str(s), str(o))
    d = json.loads(o.read_text())
    assert d["ok"] and d["output"] == "x\n" and d["result"] == {"n": 2}
    s.write_text("print('before')\n1/0\n")
    kern.run(str(s), str(o))
    d = json.loads(o.read_text())
    assert not d["ok"] and "ZeroDivisionError" in d["traceback"] and d["output"] == "before\n"
    assert sys.stdout is sys.__stdout__ or sys.stdout is not None


def test_dispatcher_waits_for_idle_and_one_at_a_time(tmp_path):
    core.ensure_dirs(str(tmp_path))
    live = str(tmp_path)
    for n in ("b", "a"):
        (tmp_path / "inbox" / f"{n}.py").write_text("pass")
    (tmp_path / "inbox" / "c.part").write_text("partial")
    sent, state = [], {"idle": False}
    d = core.Dispatcher("K", sent.append, lambda: state["idle"], live=live)
    assert d.tick() is None and sent == []
    state["idle"] = True
    assert d.tick() == "a" and len(sent) == 1 and "mcp_live_kernel.run" in sent[0]
    assert (tmp_path / "log" / "a.py").exists() and not (tmp_path / "inbox" / "a.py").exists()
    assert d.tick() is None  # a is in flight
    (tmp_path / "outbox" / "a.json").write_text("{}")
    assert d.tick() == "b" and (tmp_path / "inbox" / "c.part").exists()


def test_dispatcher_releases_stuck_script(tmp_path):
    core.ensure_dirs(str(tmp_path))
    (tmp_path / "inbox" / "a.py").write_text("pass")
    (tmp_path / "inbox" / "b.py").write_text("pass")
    now = [0]
    d = core.Dispatcher("K", lambda c: None, lambda: True, live=str(tmp_path), clock=lambda: now[0])
    assert d.tick() == "a" and d.tick() is None
    now[0] = core.MAX_BUSY_S + 1
    assert d.tick() == "b"


def test_heartbeat_written_atomically(tmp_path):
    core.write_heartbeat(str(tmp_path), now=123.5)
    assert (tmp_path / "heartbeat.txt").read_text() == "123.500" and not (tmp_path / "heartbeat.tmp").exists()


def test_plugin_file_compiles_and_server_registers_cae_live():
    compile((PLUG / "mcp_live_plugin.py").read_text(), "p", "exec")
    from abaqus_mcp.server import build
    import asyncio
    svc = type("S", (), {})
    from abaqus_mcp.service import Service
    names = [t.name for t in asyncio.run(build(Service.__new__(Service)).list_tools())]
    assert "cae_live" in names
