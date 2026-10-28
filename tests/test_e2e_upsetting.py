"""C7 end to end: frictionless upsetting of a half-height cylinder through the MCP tools.

Runs only with ABAQUS_E2E=1. Units mm, N, MPa. Frame: axisymmetric, x radial, y axial (the axis
is x = 0), symmetry plane y = 0, plate at y = 10 moving in -y. Observed sign: plate RF2 < 0 (constraint force on the RP,
opposing the plate motion; the test uses |RF2|), U2 < 0. Abaqus reports axisymmetric RF as the 360 deg total.
Fixtures: the .sta, .msg and .dat of both runs are copied to tests/fixtures/upsetting/.
"""
import asyncio
import json
import math
import os
import re
import shutil
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.skipif(os.environ.get("ABAQUS_E2E") != "1", reason="set ABAQUS_E2E=1 (needs VM + Abaqus)")

R0, H0, SY, DISP = 10.0, 20.0, 250.0, 5.0
N = 10  # elements per direction
FIX = Path(__file__).parent / "fixtures" / "upsetting"


def force(disp):
    return SY * math.pi * R0**2 * H0 / (H0 - 2 * disp)  # h = H0 - 2*disp, half model moves disp


def make_inp(first_inc):
    nid = lambda i, j: j * (N + 1) + i + 1
    L = ["*Heading", "Frictionless upsetting, half height, CAX4R", "*Node"]
    for j in range(N + 1):
        for i in range(N + 1):
            L.append(f"{nid(i, j)}, {R0 * i / N}, {H0 / 2 * j / N}")
    L.append("1000, 0., 10.")
    L.append("*Element, type=CAX4R")
    e = 0
    for j in range(N):
        for i in range(N):
            e += 1
            L.append(f"{e}, {nid(i, j)}, {nid(i + 1, j)}, {nid(i + 1, j + 1)}, {nid(i, j + 1)}")
    L += ["*Elset, elset=ALL, generate", f"1, {e}, 1",
          "*Nset, nset=AXIS", ", ".join(str(nid(0, j)) for j in range(N + 1)),
          "*Nset, nset=BOT", ", ".join(str(nid(i, 0)) for i in range(N + 1)),
          "*Nset, nset=RP", "1000",
          "*Solid Section, elset=ALL, material=STEEL", ",",
          "*Material, name=STEEL", "*Elastic", "210000., 0.3", "*Plastic", "250., 0.",
          "*Surface, type=ELEMENT, name=TOP"]
    L += [f"{(N - 1) * N + i + 1}, S3" for i in range(N)]
    L += ["*Surface, type=SEGMENTS, name=PLATE", "START, 15., 10.", "LINE, 0., 10.",
          "*Rigid Body, ref node=1000, analytical surface=PLATE",
          "*Surface Interaction, name=FRL", "*Contact Pair, interaction=FRL", "TOP, PLATE",
          "*Boundary", "AXIS, 1, 1", "BOT, 2, 2", "RP, 1, 1", "RP, 6, 6",
          "*Step, name=Upset, nlgeom=YES, inc=1000", "*Static", f"{first_inc}, 1., 1e-05, {min(first_inc, 0.02) if first_inc < 1 else 1.}",
          "*Boundary", f"RP, 2, 2, {-DISP}",
          "*Output, history, frequency=1", "*Node Output, nset=RP", "RF2, U2",
          "*Energy Output", "ALLAE, ALLIE, ALLKE, ALLPD, ALLSE, ALLWK, ALLVD, ETOTAL",
          "*Output, field, frequency=5", "*Node Output", "U, RF", "*Element Output", "S, PEEQ",
          "*Node Print, nset=RP, frequency=1", "RF2, U2",
          "*End Step"]
    return "\n".join(L) + "\n"


def call(tool, **args):
    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "abaqus_mcp.server"], env=dict(os.environ))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(tool, args)
                return json.loads(res.content[0].text)
    return asyncio.run(asyncio.wait_for(go(), 3600))


def fetch(job):
    from abaqus_mcp.config import load
    from abaqus_mcp.transport import SshTransport
    cfg = load()
    t = SshTransport(cfg.ssh_host)
    FIX.mkdir(parents=True, exist_ok=True)
    for ext in ("sta", "msg", "dat"):
        t.get(f"{cfg.work_vm}\\{job}\\{job}.{ext}", FIX / f"{job}.{ext}")


def dat_table(job):
    """{time: RF2} from the *NODE PRINT table: rows 'INCREMENT n SUMMARY' then '1000 value value'."""
    out, t = {}, None
    for line in (FIX / f"{job}.dat").read_text(errors="replace").splitlines():
        m = re.match(r"\s*STEP TIME COMPLETED\s+([^\s,]+)", line)
        if m:
            t = float(m.group(1))
        m = re.match(r"\s*1000\s+(\S+)\s+(\S+)\s*$", line)
        if m and t is not None:
            out[t] = abs(float(m.group(1)))
    return out


def dat_raw(job):
    """{time: printed RF2 string} from the .dat, same rows as dat_table."""
    out, t = {}, None
    for line in (FIX / f"{job}.dat").read_text(errors="replace").splitlines():
        m = re.match(r"\s*STEP TIME COMPLETED\s+([^\s,]+)", line)
        if m:
            t = float(m.group(1))
        m = re.match(r"\s*1000\s+(\S+)\s+(\S+)\s*$", line)
        if m and t is not None:
            out[t] = m.group(1)
    return out


def run(tmp_path, job, first_inc):
    inp = tmp_path / f"{job}.inp"
    inp.write_text(make_inp(first_inc))
    st = call("submit_job", job=job, inp_file=str(inp))
    fetch(job)
    return st


def test_upsetting(tmp_path):
    st = run(tmp_path, "upsetting", 0.01)
    assert st["status"] == "completed", st
    tab = dat_table("upsetting")
    assert tab, "no RF2 rows in .dat"
    for d in (1, 3, 5):
        t = d / DISP
        key = min(tab, key=lambda k: abs(k - t))
        assert abs(key - t) < 1e-6
        print(f"disp {d}: RF2 {tab[key]:.1f} N expected {force(d):.1f} err {100 * (tab[key] / force(d) - 1):.2f} %")
        assert tab[key] == pytest.approx(force(d), rel=0.01)
    lst = call("odb_history", job="upsetting")
    assert lst["status"] == "ok", lst
    names = {o for regs in lst["steps"].values() for outs in regs.values() for o in outs}
    assert {"ALLIE", "ALLKE", "ALLAE"} <= names, lst
    reg = next(r for regs in lst["steps"].values() for r, outs in regs.items() if "RF2" in outs)
    h = call("odb_history", job="upsetting", region=reg, outputs=["RF2"])
    series = next(v for k, v in h["series"].items() if k.endswith("RF2"))
    assert series["n_points"] == len(series["points"]) <= 200
    raw = dat_raw("upsetting")
    assert len(raw) > 200 or len(series["points"]) >= len(raw)  # uncut when the run has <= 200 points
    by_t = {round(t, 6): v for t, v in series["points"]}
    for t, printed in raw.items():
        # the odb stores single precision (rel. 6e-8), the .dat prints 8 digits: agreement to 2e-7
        assert by_t[round(t, 6)] == pytest.approx(float(printed), rel=2e-7), (t, by_t[round(t, 6)], printed)
    print(f"RF2 history matches .dat at {len(raw)} increments")
    e = call("odb_history", job="upsetting", outputs=["ALLAE", "ALLIE"])
    ae, ie = (next(v for k, v in e["series"].items() if k.endswith(n))["points"][-1][1] for n in ("ALLAE", "ALLIE"))
    print(f"ALLAE {ae:.6g} ALLIE {ie:.6g} ALLAE/ALLIE {ae / ie:.4g}")
    u = call("odb_query", job="upsetting", step="Upset", frame=-1, variable="U", set_name="RP", component="U2")
    assert u["status"] == "ok", u
    assert u["values"][0]["data"] == pytest.approx(-DISP, rel=1e-6)


def test_upsetting_cutbacks(tmp_path):
    st = run(tmp_path, "upsetting-cutback", 1.0)
    assert st["status"] == "completed", st
    assert re.search(r"^\s*1\s+1\s+1U", (FIX / "upsetting-cutback.sta").read_text(), re.M), "no cut-back forced"
