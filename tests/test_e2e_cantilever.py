"""C6 end to end through the MCP tools (stdio client -> server -> SSH -> Abaqus in the VM).

Runs only with ABAQUS_E2E=1 (each call sets a temporary project directory under $HOME), on a host with the VM up, config.local.toml filled in and
Abaqus installed. Frame: x along the beam, load in -y at the tip, bending about z.
Expected sign: tip U2 < 0, so the test compares |U2|.
"""
import asyncio
import json
import math
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from abaqus_mcp.config import load
from abaqus_mcp.service import project_key
from abaqus_mcp.transport import SshTransport
from conftest import e2e_project

pytestmark = pytest.mark.skipif(os.environ.get("ABAQUS_E2E") != "1", reason="set ABAQUS_E2E=1 (needs VM + Abaqus)")

# Hand calc (SI: m, N, kg)
L, A_SIDE, E, RHO, P = 1.0, 0.02, 210e9, 7850.0, 100.0
I = A_SIDE**4 / 12
AREA = A_SIDE**2
DELTA = P * L**3 / (3 * E * I)  # 11.905 mm
F1 = (1.8751**2 / (2 * math.pi)) * math.sqrt(E * I / (RHO * AREA * L**4))  # 16.71 Hz

BUILD = '''
from abaqus import *
from abaqusConstants import *
from caeModules import *
import mesh
m = mdb.models['Model-1']
s = m.ConstrainedSketch(name='s', sheetSize=2.0)
s.Line(point1=(0.0, 0.0), point2=(1.0, 0.0))
p = m.Part(name='Beam', dimensionality=THREE_D, type=DEFORMABLE_BODY)
p.BaseWire(sketch=s)
mat = m.Material(name='Steel')
mat.Elastic(table=((210e9, 0.3),))
mat.Density(table=((7850.0,),))
m.RectangularProfile(name='prof', a=0.02, b=0.02)
m.BeamSection(name='sec', integration=DURING_ANALYSIS, profile='prof', material='Steel')
region = p.Set(edges=p.edges, name='ALL')
p.SectionAssignment(region=region, sectionName='sec')
p.assignBeamSectionOrientation(region=region, method=N1_COSINES, n1=(0.0, 0.0, -1.0))
p.seedEdgeByNumber(edges=p.edges, number=20)
p.setElementType(regions=(p.edges,), elemTypes=(mesh.ElemType(elemCode=B33, elemLibrary=STANDARD),))
p.generateMesh()
a = m.rootAssembly
inst = a.Instance(name='Beam-1', part=p, dependent=ON)
a.Set(vertices=inst.vertices.findAt(((0.0, 0.0, 0.0),)), name='FIXED')
a.Set(vertices=inst.vertices.findAt(((1.0, 0.0, 0.0),)), name='TIP')
m.StaticStep(name='Load', previous='Initial', nlgeom=OFF)
m.FrequencyStep(name='Freq', previous='Load', numEigen=3)
m.ConcentratedForce(name='P', createStepName='Load', region=a.sets['TIP'], cf2=-100.0)
if %s:
    m.EncastreBC(name='fix', createStepName='Initial', region=a.sets['FIXED'])
mdb.saveAs(pathName='%s.cae')
'''


def call(tool, **args):
    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "abaqus_mcp.server"], env=dict(os.environ))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                assert json.loads((await s.call_tool("set_project", {"path": str(e2e_project())})).content[0].text)["status"] == "ok"
                res = await s.call_tool(tool, args)
                return json.loads(res.content[0].text)
    return asyncio.run(asyncio.wait_for(go(), 3600))


def build_and_run(tmp_path, job, bc):
    script = tmp_path / f"build_{job}.py"
    script.write_text(BUILD % (bc, job))
    r = call("run_script", job=job, script_path=str(script))
    assert r["status"] == "ok", r
    return call("submit_job", job=job, cae_file=f"{job}.cae", model="Model-1")


def test_hand_calc_values():
    assert DELTA * 1e3 == pytest.approx(11.905, rel=1e-3)
    assert F1 == pytest.approx(16.71, rel=2e-3)


def test_license():
    assert call("license_check")["status"] == "ok"


def test_cantilever(tmp_path):
    st = build_and_run(tmp_path, "cantilever", True)
    assert st["status"] == "completed", st

    info = call("model_summary", job="cantilever")
    assert "Steel" in info["materials"]
    assert {"Load", "Freq"} <= {s["name"] for s in info["steps"]}

    u = call("odb_query", job="cantilever", step="Load", frame=-1, variable="U", set_name="TIP", component="U2")
    assert u["status"] == "ok", u
    assert abs(u["values"][0]["data"]) == pytest.approx(DELTA, rel=0.01)

    q = call("odb_query", job="cantilever", step="Freq", variable=None)
    f1 = next(f["frequency"] for f in q["frames"] if f["frequency"])
    assert f1 == pytest.approx(F1, rel=0.02)

    png = call("viewport_png", job="cantilever", step_index=0)
    assert png["status"] == "ok" and os.path.getsize(png["path"]) > 0

    # the PNG is in the project directory, the .odb in its VM mirror, nothing under ~/abaqus-work
    assert png["path"].startswith(str(e2e_project() / "cantilever"))
    assert not (Path.home() / "abaqus-work" / "cantilever").exists()
    cfg = load()
    t = SshTransport(cfg.ssh_host, cfg.max_output, cfg.ssh_config)
    odb = f"{cfg.work_vm}\\{project_key(e2e_project())}\\cantilever\\cantilever.odb"
    assert "yes" in t.run(f"if (Test-Path -LiteralPath '{odb}') {{ 'yes' }}").stdout


def test_script_error_returns_traceback(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("raise ValueError('deliberate')\n")
    r = call("run_script", job="cantilever-err", script_path=str(bad))
    assert r["status"] == "error"
    assert "ValueError" in r["traceback"] and "deliberate" in r["traceback"]


def test_missing_bc_reports_msg_error(tmp_path):
    st = build_and_run(tmp_path, "cantilever-nobc", False)
    # Abaqus/Standard 2026 reports the singularity as warnings; the .msg error is the failed
    # cut-back ("TOO MANY ATTEMPTS MADE FOR THIS INCREMENT"), see tests/fixtures/nobc.msg.
    assert st["status"] == "failed", st
    assert st["errors"], st
