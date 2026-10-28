import json
import time

from abaqus_mcp import abaqus_scripts as sc
from conftest import FIX, closed_port, ok

TB = (FIX / "cae_error.stderr").read_text()
OUT_ERR = "Abaqus Error: cae exited with an error.\n"


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
    svc, t = make(lambda c: ok(OUT_ERR, TB, 0) if "noGUI=bad.py" in c else ok("#: hi\n#* ValueError: x\n") if "Get-Content" in c and "abaqus.rpy" in c else None)
    r = svc.run_script("job1", str(s))
    assert r["status"] == "error" and r["exit_code"] == 0
    assert r["traceback"].startswith("ValueError: deliberate") and "QAE" not in r["traceback"]
    assert r["error"] == "ValueError: deliberate"
    assert t.puts["C:\\abaqus-work\\job1\\bad.py"] == "x"
    assert any(c.rstrip().endswith("abaqus.bat' cae noGUI=bad.py; exit $LASTEXITCODE") for c in t.commands)
    svc2, _ = make(lambda c: ok("#: printed line\n#: second\n#* old\n") if "Get-Content" in c else ok("done"))
    r2 = svc2.run_script("job1", str(s))
    assert r2["status"] == "ok" and r2["print_output"] == "printed line\nsecond"
    svc3, _ = make(lambda c: ok("#* ValueError: from rpy\n") if "Get-Content" in c else ok(OUT_ERR, "")) 
    assert svc3.run_script("job1", str(s))["traceback"] == "ValueError: from rpy"


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
    assert "TOO MANY ATTEMPTS" in r["errors"][0] and "NUMERICAL SINGULARITY" in r["warnings"][0]


def test_submit_inp_foreground(make, tmp_path):
    inp = tmp_path / "model.inp"
    inp.write_text("*HEADING")
    svc, t = make(lambda c: ok(status_out((FIX / "ok.sta").read_text())) if "===STA===" in c else None)
    r = svc.submit_job("jb", inp_file=str(inp))
    assert r["status"] == "completed" and r["exit_code"] == 0
    assert "C:\\abaqus-work\\jb\\jb.inp" in t.puts
    assert any("abaqus.bat' job=jb input=jb.inp cpus=1 interactive" in c for c in t.commands)
    assert any("Remove-Item" in c and "jb.lck" in c for c in t.commands)


def test_submit_cae_background(make, tmp_path):
    cae = tmp_path / "m.cae"
    cae.write_text("x")
    svc, t = make(lambda c: ok(f"{sc.START}\n" + '{"inp": "jb.inp"}' + f"\n{sc.END}") if "_write_inp" in c else None)
    r = svc.submit_job("jb", cae_file=str(cae), model="Model-1", background=True)
    assert r["status"] == "started"
    assert '\\"cae\\": \\"m.cae\\"' in t.puts["C:\\abaqus-work\\jb\\_write_inp.py"]
    bg = [c for c in t.commands if "Win32_Process" in c]
    assert bg and "Invoke-CimMethod" in bg[0] and "Start-Process" not in bg[0]
    assert "CurrentDirectory='C:\\abaqus-work\\jb'" in bg[0]
    assert 'abaqus.bat" job=jb input=jb.inp cpus=1 interactive > "jb.log" 2>&1' in bg[0]


def test_submit_argument_check(make):
    svc, _ = make()
    assert svc.submit_job("j")["status"] == "error"


def _json(d):
    return ok(f"banner\n{sc.START}\n{json.dumps(d)}\n{sc.END}\n")


ODB_JSON = "C:\\abaqus-work\\jb\\_odb_query.json"


def test_odb_query(make):
    data = {"step": "Step-1", "n_frames": 2, "frames": [], "values": [{"label": 21, "data": -0.0119}]}
    svc, t = make()
    t.files[ODB_JSON] = json.dumps(data)
    r = svc.odb_query("jb", "Step-1", variable="U", set_name="TIP", component="U2")
    assert r["status"] == "ok" and r["values"][0]["data"] == -0.0119
    script = t.puts["C:\\abaqus-work\\jb\\_odb_query.py"]
    assert "readOnly=True" in script and '\\"component\\": \\"U2\\"' in script
    assert '\\"result\\": \\"_odb_query.json\\"' in script
    assert t.commands[-1].rstrip().endswith("odb_query.py; exit $LASTEXITCODE") and " python _odb_query.py" in t.commands[-1]
    compile(script, "s", "exec")


def test_odb_query_over_300_rows_not_truncated(make):
    rows = [{"label": i, "data": [0.1 * i, 0.0, 0.0]} for i in range(1, 501)]
    data = {"step": "S", "n_frames": 1, "frames": [], "n_values": 500, "values": rows}
    # stdout is bounded by the transport (max_output); the rows travel in the file
    svc, t = make(lambda c: ok("x" * 50000) if " python " in c else None)
    t.files[ODB_JSON] = json.dumps(data)
    r = svc.odb_query("jb", "S", max_values=500)
    assert r["status"] == "ok" and len(r["values"]) == 500 and r["values"][-1]["label"] == 500


def test_odb_query_error_and_bad_input(make):
    svc, t = make()
    t.files[ODB_JSON] = json.dumps({"error": "set not found: X"})
    assert svc.odb_query("jb", "Step-1", set_name="X")["status"] == "error"
    assert svc.odb_query("jb", "Step 1")["status"] == "error"
    svc, _ = make(lambda c: ok("no json", TB, 1) if " python " in c else None)
    r = svc.odb_query("jb", "Step-1")
    assert r["status"] == "error" and "ValueError" in r["hint"]


def test_model_info(make):
    svc, t = make()
    t.files["C:\\abaqus-work\\jb\\_model_info.json"] = json.dumps({"models": {"Model-1": {"steps": {}}}})
    r = svc.model_info("jb")
    assert "Model-1" in r["models"] and t.commands[-1].rstrip().endswith("cae noGUI=_model_info.py; exit $LASTEXITCODE")


def test_abaqus_cmd_full_path_and_missing(make):
    svc, t = make(abaqus_cmd="D:\\x y\\abaqus.bat")
    svc._abq("C:\\w", "information=release", 5)
    c = t.commands[-1]
    assert "Test-Path -LiteralPath 'D:\\x y\\abaqus.bat'" in c and "& 'D:\\x y\\abaqus.bat' information=release" in c
    assert "abaqus not found" in c and "exit 127" in c


def test_bare_cae_name_not_resolved_against_cwd(make, tmp_path, monkeypatch):
    (tmp_path / "bare.cae").write_text("host copy")
    monkeypatch.chdir(tmp_path)
    svc, t = make()
    svc.model_info("jb", cae_file="bare.cae")
    assert not any(k.endswith("bare.cae") for k in t.puts)
    assert '\\"cae\\": \\"bare.cae\\"' in t.puts["C:\\abaqus-work\\jb\\_model_info.py"]
    svc.model_info("jb", cae_file=str(tmp_path / "bare.cae"))
    assert "C:\\abaqus-work\\jb\\bare.cae" in t.puts


def test_name_must_start_with_letter(make):
    svc, t = make()
    assert svc.job_status("-Force")["status"] == "error" and svc.job_status("1a")["status"] == "error"
    assert t.commands == []


def test_scripts_frame_and_viewport_rules():
    q = sc.odb_query("a.odb", "S", result="r.json")
    assert "len(step.frames)" in q
    v = sc.viewport("a.odb", "o")
    assert "CONTOURS_ON_DEF" in v and "from abaqus import *" in v and "Magnitude\"" in v and "len(odb.steps[sname].frames)" in v
    for m in (sc.model_info("a.cae"), sc.write_inp("a.cae", "M", "j")):
        assert "mdb = openMdb(pathName=" in m and "from abaqus import *" in m
    assert "element_sets" not in sc.model_info("a.cae")


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
