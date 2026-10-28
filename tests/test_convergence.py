"""C5: job_status convergence detail on the real upsetting fixtures. Expected numbers come from
awk/grep written from the definitions in .team/goal.md, never from the parser."""
import json
import os
import subprocess

import pytest
from conftest import FIX, ok

from test_tools import status_out

pytestmark = pytest.mark.skipif(os.name == "nt", reason="awk/grep oracle: Linux only")

U = FIX / "upsetting"
ROW = '$1~/^[0-9]+$/ && $2~/^[0-9]+$/ && $3~/^[0-9]+U?$/ && NF>=9'


def awk(prog, path):
    return subprocess.run(["awk", prog, str(path)], capture_output=True, text=True, check=True).stdout.split()


def expected(job):
    sta = U / f"{job}.sta"
    g = lambda body: awk(f"{ROW} {{ {body} }}", sta)
    attempts = int(awk(f"{ROW} {{n++}} END {{print n+0}}", sta)[0])
    cut = int(awk(f"{ROW} && $3~/U$/ {{n++}} END {{print n+0}}", sta)[0])
    done = lambda body, end: awk(f"{ROW} && $3!~/U$/ {{ {body} }} END {{ {end} }}", sta)[0]
    return {
        "attempts": attempts, "cutbacks": cut, "increments_done": attempts - cut,
        "equil_iters_max": int(awk(f"{ROW} && $5>m {{m=$5}} END {{print m}}", sta)[0]),
        "equil_iters_mean": float(awk(f"{ROW} {{s+=$5;n++}} END {{printf \"%.2f\", s/n}}", sta)[0]),
        "severe_iters": int(awk(f"{ROW} {{s+=$4}} END {{print s+0}}", sta)[0]),
        "min_increment": float(done("if (m==\"\"||$9<m) m=$9", "print m")),
        "last_increment": float(done("l=$9", "print l")),
        "step_time": float(done("t=$8", "print t")),
    }


def warnings(job):
    msg = U / f"{job}.msg"
    cnt = lambda pat: int(subprocess.run(f"grep -c '\\*\\*\\*WARNING.*{pat}' {msg}; true", shell=True, capture_output=True,
                                         text=True).stdout)
    first = lambda pat: int(awk(f"/^ *INCREMENT +[0-9]+ +STARTS/ {{i=$2}} /\\*\\*\\*WARNING.*{pat}/ {{print i; exit}}", msg)[0])
    return cnt, first


@pytest.mark.parametrize("job", ["upsetting", "upsetting-cutback"])
def test_sta_counts_match_awk(make, job):
    want = expected(job)
    svc, _ = make(lambda c: ok(status_out((U / f"{job}.sta").read_text(), (U / f"{job}.msg").read_text())))
    r = svc.job_status("j")
    got = r["steps"]["1"]
    for k, v in want.items():
        assert got[k] == pytest.approx(v), k
    assert r["status"] == "completed"
    assert len(json.dumps(r, indent=2).splitlines()) < 100


def test_cutback_fixture_has_cutbacks():
    assert expected("upsetting")["cutbacks"] == 0
    assert expected("upsetting-cutback")["cutbacks"] == 1


def test_msg_warning_groups(make):
    cnt, first = warnings("upsetting-cutback")
    svc, _ = make(lambda c: ok(status_out((U / "upsetting-cutback.sta").read_text(), (U / "upsetting-cutback.msg").read_text())))
    g = {x["warning"]: x for x in svc.job_status("j")["warning_groups"]}
    for name, pat in (("negative eigenvalues", "NEGATIVE EIGENVALUES"), ("plasticity strain increment", "STRAIN INCREMENT HAS EXCEEDED")):
        assert g[name]["count"] == cnt(pat) > 0
        assert g[name]["first_increment"] == first(pat)
    assert sum(x["count"] for x in g.values()) == cnt("")
    svc, _ = make(lambda c: ok(status_out((U / "upsetting.sta").read_text(), (U / "upsetting.msg").read_text())))
    assert "warning_groups" not in svc.job_status("j")


def test_other_warning_grouped_by_first_line_without_numbers(make):
    msg = " INCREMENT 3 STARTS. ATTEMPT NUMBER 1, TIME INCREMENT 0.1\n ***WARNING: ELEMENT 12 IS TOO ODD AT 4.5E-3\n\n" \
          " ***WARNING: ELEMENT 99 IS TOO ODD AT 7\n"
    svc, _ = make(lambda c: ok(status_out("", msg)))
    g = svc.job_status("j")["warning_groups"]
    assert g == [{"warning": "ELEMENT IS TOO ODD AT", "count": 2, "first_step": 0, "first_increment": 3}]


def test_dat_only_input_error(make):
    dat = " ***ERROR: THE KEYWORD *FOO IS NOT RECOGNIZED\n             LINE 12\n"
    svc, _ = make(lambda c: ok(f"===STA===\n===MSG===\n===DAT===\n{dat}===LCK===\n===END===\n"))
    r = svc.job_status("j")
    assert r["status"] == "failed" and "*FOO" in r["errors"][0] and "LINE 12" in r["errors"][0]
