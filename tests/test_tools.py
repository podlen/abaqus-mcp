import json
import time

from abaqus_mcp import abaqus_scripts as sc
from conftest import FIX, closed_port, ok

TB = 'Traceback (most recent call last):\n  File "bad.py", line 1, in <module>\nNameError: name \'x\' is not defined\n'


def status_out(sta="", msg="", lck=False):
    return f"===STA===\n{sta}\n===MSG===\n{msg}\n===LCK===\n{'yes' if lck else ''}\n===END===\n"


def test_license_ok_no_vpn(make):
    svc, _ = make()
    assert svc.license_check() == {"status": "ok", "license": "reachable", "vpn_started": False}


def test_license_closed_runs_vpn_once_then_errors_within_30s(make, tmp_path):
    marker = tmp_path / "calls"
    vpn = tmp_path / "abaqus-vpn"
    vpn.write_text(f'#!/bin/sh\necho "$1" >> {marker}\n')
    vpn.chmod(0o755)
    svc, _ = make(port=closed_port(), vpn_cmd=str(vpn))
    t0 = time.monotonic()
    r = svc.license_check()
    assert time.monotonic() - t0 < 30
    assert r["status"] == "error" and "license server unreachable" in r["error"]
    assert marker.read_text().split() == ["up"]


def test_license_vpn_reconnect_passes(make, tmp_path, monkeypatch):
    vpn = tmp_path / "abaqus-vpn"
    vpn.write_text("#!/bin/sh\nexit 0\n")
    vpn.chmod(0o755)
    svc, _ = make(vpn_cmd=str(vpn))
    answers = iter([False, True])
    monkeypatch.setattr(svc, "_probe", lambda t: next(answers))
    assert svc.license_check() == {"status": "ok", "license": "reachable", "vpn_started": True}


def test_guard_blocks_run_script_and_submit(make, tmp_path):
    svc, t = make(port=closed_port(), vpn_cmd="/nonexistent")
    s = tmp_path / "a.py"
    s.write_text("print(1)")
    assert "unreachable" in svc.run_script("j", str(s))["error"]
    assert "unreachable" in svc.submit_job("j", inp_file=str(s))["error"]
    assert t.commands == []


def test_run_script_ok_and_traceback(make, tmp_path):
    s = tmp_path / "bad.py"
    s.write_text("x")
    svc, t = make(lambda c: ok("", TB, 1) if "noGUI=bad.py" in c else None)
    r = svc.run_script("job1", str(s))
    assert r["status"] == "error" and r["exit_code"] == 1
    assert r["traceback"].endswith("NameError: name 'x' is not defined") and "NameError" in r["error"]
    assert t.puts["C:\\abaqus-work\\job1\\bad.py"] == "x"
    assert any(c.rstrip().endswith("abaqus cae noGUI=bad.py; exit $LASTEXITCODE") for c in t.commands)
    svc2, _ = make(lambda c: ok("done"))
    assert svc2.run_script("job1", str(s))["status"] == "ok"


def test_run_script_rejects_bad_job(make, tmp_path):
    s = tmp_path / "a.py"
    s.write_text("")
    svc, t = make()
    assert svc.run_script("a;calc", str(s))["status"] == "error"
    assert t.commands == []


def test_job_status_variants(make):
    cases = [
        (status_out((FIX / "ok.sta").read_text()), "completed"),
        (status_out((FIX / "running.sta").read_text(), lck=True), "running"),
        (status_out((FIX / "failed.sta").read_text(), (FIX / "nobc.msg").read_text()), "failed"),
        (status_out(), "not_found"),
    ]
    for out, want in cases:
        svc, _ = make(lambda c, out=out: ok(out))
        assert svc.job_status("j")["status"] == want
    svc, _ = make(lambda c: ok(status_out("", (FIX / "nobc.msg").read_text())))
    r = svc.job_status("j")
    assert "NUMERICAL SINGULARITY" in r["errors"][0]


def test_submit_inp_foreground(make, tmp_path):
    inp = tmp_path / "model.inp"
    inp.write_text("*HEADING")
    svc, t = make(lambda c: ok(status_out((FIX / "ok.sta").read_text())) if "===STA===" in c else None)
    r = svc.submit_job("jb", inp_file=str(inp))
    assert r["status"] == "completed" and r["exit_code"] == 0
    assert "C:\\abaqus-work\\jb\\jb.inp" in t.puts
    assert any("abaqus job=jb input=jb.inp cpus=1 interactive" in c for c in t.commands)
    assert any("Remove-Item" in c and "jb.lck" in c for c in t.commands)


def test_submit_cae_background(make, tmp_path):
    cae = tmp_path / "m.cae"
    cae.write_text("x")
    svc, t = make(lambda c: ok(f"{sc.START}\n" + '{"inp": "jb.inp"}' + f"\n{sc.END}") if "_write_inp" in c else None)
    r = svc.submit_job("jb", cae_file=str(cae), model="Model-1", background=True)
    assert r["status"] == "started"
    assert '\\"cae\\": \\"m.cae\\"' in t.puts["C:\\abaqus-work\\jb\\_write_inp.py"]
    assert any("Start-Process" in c and "abaqus job=jb input=jb.inp" in c for c in t.commands)


def test_submit_argument_check(make):
    svc, _ = make()
    assert svc.submit_job("j")["status"] == "error"


def _json(d):
    return ok(f"banner\n{sc.START}\n{json.dumps(d)}\n{sc.END}\n")


def test_odb_query(make):
    data = {"step": "Step-1", "n_frames": 2, "frames": [], "values": [{"label": 21, "data": -0.0119}]}
    svc, t = make(lambda c: _json(data))
    r = svc.odb_query("jb", "Step-1", variable="U", set_name="TIP", component="U2")
    assert r["status"] == "ok" and r["values"][0]["data"] == -0.0119
    script = t.puts["C:\\abaqus-work\\jb\\_odb_query.py"]
    assert "readOnly=True" in script and '\\"component\\": \\"U2\\"' in script
    assert t.commands[-1].rstrip().endswith("abaqus python _odb_query.py; exit $LASTEXITCODE")
    compile(script, "s", "exec")


def test_odb_query_error_and_bad_input(make):
    svc, _ = make(lambda c: _json({"error": "set not found: X"}))
    assert svc.odb_query("jb", "Step-1", set_name="X")["status"] == "error"
    assert svc.odb_query("jb", "Step 1")["status"] == "error"
    svc, _ = make(lambda c: ok("no json", TB, 1) if "python" in c else None)
    r = svc.odb_query("jb", "Step-1")
    assert r["status"] == "error" and "NameError" in r["hint"]


def test_model_info(make):
    svc, t = make(lambda c: _json({"models": {"Model-1": {"steps": {}}}}))
    r = svc.model_info("jb")
    assert "Model-1" in r["models"] and t.commands[-1].rstrip().endswith("abaqus cae noGUI=_model_info.py; exit $LASTEXITCODE")


def test_viewport_png(make):
    svc, t = make(lambda c: _json({"ok": True, "file": "jb_view.png"}))
    r = svc.viewport_png("jb")
    assert r["status"] == "ok" and r["path"].endswith("jb_view.png")
    s = t.puts["C:\\abaqus-work\\jb\\_viewport.py"]
    assert '\\"out\\": \\"jb_view\\"' in s and "maximize" not in s
    assert t.gets == ["C:\\abaqus-work\\jb\\jb_view.png"]
    svc, _ = make(lambda c: _json({"ok": False}))
    assert svc.viewport_png("jb")["status"] == "error"


def test_abaqus_scripts_compile():
    for s in (sc.odb_query("a.odb", "S"), sc.model_info("a.cae"), sc.write_inp("a.cae", "M", "j"), sc.viewport("a.odb", "o")):
        compile(s, "s", "exec")
