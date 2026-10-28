import hashlib
import json
import os
import re
import time
from pathlib import Path

import pytest

from abaqus_mcp import abaqus_scripts as sc
from abaqus_mcp.service import project_key
from conftest import FIX, closed_port, ok

posix = pytest.mark.skipif(os.name == "nt", reason="needs a /bin/sh script")

TB = (FIX / "cae_error.stderr").read_text()
OUT_ERR = "Abaqus Error: cae exited with an error.\n"


def status_out(sta="", msg="", lck=False):
    return f"===STA===\n{sta}\n===MSG===\n{msg}\n===LCK===\n{'yes' if lck else ''}\n===END===\n"


def test_license_ok_no_vpn(make):
    svc, _ = make()
    assert svc.license_check() == {"status": "ok", "license": "reachable", "vpn_started": False}


@posix
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


@posix
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
    assert t.puts[svc.vm_root + "\\job1\\bad.py"] == "x"
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
    assert svc.vm_root + "\\jb\\jb.inp" in t.puts
    assert any("abaqus.bat' job=jb input=jb.inp cpus=1 interactive" in c for c in t.commands)
    assert any("Remove-Item" in c and "jb.lck" in c for c in t.commands)


def test_submit_cae_background(make, tmp_path):
    cae = tmp_path / "m.cae"
    cae.write_text("x")
    svc, t = make(lambda c: ok(f"{sc.START}\n" + '{"inp": "jb.inp"}' + f"\n{sc.END}") if "_write_inp" in c else None)
    r = svc.submit_job("jb", cae_file=str(cae), model="Model-1", background=True)
    assert r["status"] == "started"
    assert '\\"cae\\": \\"m.cae\\"' in t.puts[svc.vm_root + "\\jb\\_write_inp.py"]
    bg = [c for c in t.commands if "Win32_Process" in c]
    assert bg and "Invoke-CimMethod" in bg[0] and "Start-Process" not in bg[0]
    assert f"CurrentDirectory='{svc.vm_root}\\jb'" in bg[0]
    assert 'abaqus.bat" job=jb input=jb.inp cpus=1 interactive > "jb.log" 2>&1' in bg[0]


def test_submit_argument_check(make):
    svc, _ = make()
    assert svc.submit_job("j")["status"] == "error"


def _json(d):
    return ok(f"banner\n{sc.START}\n{json.dumps(d)}\n{sc.END}\n")


def ODB_JSON(svc):
    return svc.vm_root + "\\jb\\_odb_query.json"


def test_odb_query(make):
    data = {"step": "Step-1", "n_frames": 2, "frames": [], "values": [{"label": 21, "data": -0.0119}]}
    svc, t = make()
    t.files[ODB_JSON(svc)] = json.dumps(data)
    r = svc.odb_query("jb", "Step-1", variable="U", set_name="TIP", component="U2")
    assert r["status"] == "ok" and r["values"][0]["data"] == -0.0119
    script = t.puts[svc.vm_root + "\\jb\\_odb_query.py"]
    assert "readOnly=True" in script and '\\"component\\": \\"U2\\"' in script
    assert '\\"result\\": \\"_odb_query.json\\"' in script
    assert t.commands[-1].rstrip().endswith("odb_query.py; exit $LASTEXITCODE") and " python _odb_query.py" in t.commands[-1]
    compile(script, "s", "exec")


def test_odb_query_over_300_rows_not_truncated(make):
    rows = [{"label": i, "data": [0.1 * i, 0.0, 0.0]} for i in range(1, 501)]
    data = {"step": "S", "n_frames": 1, "frames": [], "n_values": 500, "values": rows}
    # stdout is bounded by the transport (max_output); the rows travel in the file
    svc, t = make(lambda c: ok("x" * 50000) if " python " in c else None)
    t.files[ODB_JSON(svc)] = json.dumps(data)
    r = svc.odb_query("jb", "S", max_values=500)
    assert r["status"] == "ok" and len(r["values"]) == 500 and r["values"][-1]["label"] == 500


def test_odb_query_error_and_bad_input(make):
    svc, t = make()
    t.files[ODB_JSON(svc)] = json.dumps({"error": "set not found: X"})
    assert svc.odb_query("jb", "Step-1", set_name="X")["status"] == "error"
    assert svc.odb_query("jb", "Step 1")["status"] == "error"
    svc, _ = make(lambda c: ok("no json", TB, 1) if " python " in c else None)
    r = svc.odb_query("jb", "Step-1")
    assert r["status"] == "error" and "ValueError" in r["hint"]


def test_model_summary(make):
    svc, t = make()
    t.files[svc.vm_root + "\\jb\\_model_summary.json"] = json.dumps({"source": "jb.cae", "model": "Model-1"})
    r = svc.model_summary("jb")
    assert r["status"] == "ok" and r["model"] == "Model-1"
    assert t.commands[-1].rstrip().endswith("cae noGUI=_model_summary.py; exit $LASTEXITCODE")
    s = t.puts[svc.vm_root + "\\jb\\_model_summary.py"]
    assert '\\"cae\\": \\"jb.cae\\"' in s and '\\"model\\": null' in s and "def model_summary(mdb" in s
    svc.model_summary("jb", model="Solid")
    assert '\\"model\\": \\"Solid\\"' in t.puts[svc.vm_root + "\\jb\\_model_summary.py"]
    assert svc.model_summary("jb", model="a;b")["status"] == "error"


def test_model_summary_kernel_function_has_no_noGUI_calls():
    src = sc._kernel("summary.py").split('"""', 2)[2]  # code after the module docstring
    for bad in ("openMdb", "session", "noGUI", "from abaqus import", "sys.__stdout__"):
        assert bad not in src
    compile(src, "summary.py", "exec")


def test_model_views(make):
    svc, t = make(lambda c: _json({"ok": True, "shown": "assembly", "files": []}))
    r = svc.model_views("jb", highlight="TOP")
    assert r["status"] == "ok" and r["highlight"] == "TOP" and r["shown"] == "assembly"
    assert set(r["paths"]) == {"iso", "front", "top"} and r["paths"]["iso"].endswith("jb_views_TOP_iso.png")
    s = t.puts[svc.vm_root + "\\jb\\_model_views.py"]
    assert '\\"base\\": \\"jb_views_TOP\\"' in s and "maximize(" not in s and "def render_views(" in s
    assert t.gets == [svc.vm_root + f"\\jb\\jb_views_TOP_{v}.png" for v in ("iso", "front", "top")]
    assert svc.model_views("jb", highlight="a b")["status"] == "error"
    svc, _ = make(lambda c: _json({"ok": False}))
    assert svc.model_views("jb")["status"] == "error"


def test_model_views_kernel_function_rules():
    src = sc._kernel("views.py").split('"""', 2)[2]
    assert "maximize(" not in src and "openMdb" not in src and "noGUI" not in src
    compile(src, "views.py", "exec")


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
    svc.model_summary("jb", cae_file="bare.cae")
    assert not any(k.endswith("bare.cae") for k in t.puts)
    assert '\\"cae\\": \\"bare.cae\\"' in t.puts[svc.vm_root + "\\jb\\_model_summary.py"]
    svc.model_summary("jb", cae_file=str(tmp_path / "bare.cae"))
    assert svc.vm_root + "\\jb\\bare.cae" in t.puts


def test_bare_names_found_in_project_dir(make):
    svc, t = make()
    (svc.project / "m.inp").write_text("*HEADING")
    (svc.project / "b.cae").write_text("x")
    (svc.project / "s.py").write_text("print(1)")
    svc.submit_job("jb", inp_file="m.inp")
    assert t.puts[svc.vm_root + "\\jb\\jb.inp"] == "*HEADING"
    svc.model_summary("jb", cae_file="b.cae")
    assert svc.vm_root + "\\jb\\b.cae" in t.puts
    svc.run_script("jb", "s.py")
    assert t.puts[svc.vm_root + "\\jb\\s.py"] == "print(1)"


def test_name_must_start_with_letter(make):
    svc, t = make()
    assert svc.job_status("-Force")["status"] == "error" and svc.job_status("1a")["status"] == "error"
    assert t.commands == []


def test_scripts_frame_and_viewport_rules():
    q = sc.odb_query("a.odb", "S", result="r.json")
    assert "len(step.frames)" in q
    v = sc.viewport("a.odb", "o")
    assert "CONTOURS_ON_DEF" in v and "from abaqus import *" in v and "Magnitude\"" in v and "len(odb.steps[sname].frames)" in v
    for m in (sc.model_summary("a.cae"), sc.model_views("a.cae", "b"), sc.write_inp("a.cae", "M", "j")):
        assert "mdb = openMdb(pathName=" in m and "from abaqus import *" in m


def test_viewport_png(make):
    svc, t = make(lambda c: _json({"ok": True, "file": "jb_view.png"}))
    r = svc.viewport_png("jb")
    assert r["status"] == "ok" and r["path"].endswith("jb_view.png")
    s = t.puts[svc.vm_root + "\\jb\\_viewport.py"]
    assert '\\"out\\": \\"jb_view\\"' in s and "maximize" not in s
    assert t.gets == [svc.vm_root + "\\jb\\jb_view.png"]
    svc, _ = make(lambda c: _json({"ok": False}))
    assert svc.viewport_png("jb")["status"] == "error"


def test_abaqus_scripts_compile():
    for s in (sc.odb_query("a.odb", "S"), sc.model_summary("a.cae"), sc.model_views("a.cae", "b", highlight="S"), sc.write_inp("a.cae", "M", "j"), sc.viewport("a.odb", "o")):
        compile(s, "s", "exec")


def HIST_JSON(svc):
    return svc.vm_root + "\\jb\\_odb_history.json"


def test_odb_history(make):
    data = {"series": {"Node RIGID.1000 / RF2": {"n_points": 2, "points": [[0.0, 0.0], [1.0, -5.0]]}}}
    svc, t = make()
    t.files[HIST_JSON(svc)] = json.dumps(data)
    r = svc.odb_history("jb", step="Upset", region="rigid", outputs=["RF2"])
    assert r["status"] == "ok" and r["series"]["Node RIGID.1000 / RF2"]["points"][1] == [1.0, -5.0]
    script = t.puts[svc.vm_root + "\\jb\\_odb_history.py"]
    assert "readOnly=True" in script and '\\"outputs\\": [\\"RF2\\"]' in script and '\\"max_points\\": 200' in script
    assert t.commands[-1].rstrip().endswith("_odb_history.py; exit $LASTEXITCODE") and " python _odb_history.py" in t.commands[-1]
    assert "cae noGUI" not in t.commands[-1]
    compile(script, "s", "exec")


def test_odb_history_cut_keeps_extremes():
    ns = {}
    src = sc.odb_history("a.odb")
    exec(src.split("odb = openOdb")[0].split("from odbAccess import openOdb")[1], ns)
    pts = [[float(i), float((i * 37) % 101)] for i in range(1000)]
    cut = ns["_cut"](pts, 200)
    assert len(cut) == 200 and cut[0] == pts[0] and cut[-1] == pts[-1]
    assert max(c[1] for c in cut) == 100 and min(c[1] for c in cut) == 0


def test_odb_history_validation(make):
    svc, t = make()
    assert svc.odb_history("jb", outputs=["RF2;x"])["status"] == "error"
    assert svc.odb_history("jb", region="a'b")["status"] == "error"
    assert t.commands == []
    r = svc.odb_history("jb")  # nothing fetched: no file
    assert r["status"] == "error"


def test_summary_cut_records_omitted():
    ns = {}
    exec(sc._kernel("summary.py"), ns)
    om = {}
    assert ns["_cut"](range(50), "sets", "sets", 1.0, om) == list(range(30)) and om == {"sets": 20}
    om = {}
    assert len(ns["_cut"](range(50), "sets", "sets", 0.1, om)) == 3 and om == {"sets": 47}
    assert ns["_cut"]([1], "sets", "sets", 0.0, {}) == [1]


def test_project_key_slug_and_hash():
    p = Path("/home/u/Pläte 1_a")
    key = project_key(p)
    assert key == "Plte1_a-" + hashlib.sha1(str(p).encode()).hexdigest()[:8]
    assert re.fullmatch(r"[A-Za-z0-9_-]+-[0-9a-f]{8}", key)
    assert project_key(Path("/home/u/ü")).startswith("project-")


def test_set_project_vm_dir_and_switch(make):
    svc, _ = make()
    home = Path.home()
    a = svc.set_project(str(home / "a"))
    assert a["status"] == "ok" and a["vm_dir"] == f"C:\\abaqus-work\\{project_key(home.resolve() / 'a')}"
    assert (home / "a").is_dir()
    svc.set_project(str(home / "b"))
    assert svc.vm_root.endswith(project_key(home.resolve() / "b"))
    assert svc._host("jb") == home.resolve() / "b" / "jb"


def test_set_project_limited_to_home(make, tmp_path):
    svc, _ = make(project=False)
    (tmp_path / "outside").mkdir()
    r = svc.set_project(str(tmp_path / "outside"))
    assert r["status"] == "error" and "home" in r["error"]
    link = Path.home() / "link"
    link.symlink_to(tmp_path / "outside")
    assert svc.set_project(str(link))["status"] == "error"  # symlinks are followed
    assert svc.project is None


def test_no_project_error(make, tmp_path):
    svc, t = make(project=False)
    s = tmp_path / "a.py"
    s.write_text("")
    calls = [lambda: svc.run_script("j", str(s)), lambda: svc.submit_job("j", inp_file=str(s)),
             lambda: svc.job_status("j"), lambda: svc.odb_query("j", "Step-1"), lambda: svc.odb_history("j"),
             lambda: svc.model_summary("j", live=False), lambda: svc.model_views("j", live=False),
             lambda: svc.viewport_png("j")]
    for c in calls:
        r = c()
        assert r["status"] == "error" and r["error"] == "no project: call set_project"
    assert t.commands == []
