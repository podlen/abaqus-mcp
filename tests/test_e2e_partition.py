"""Spec 005 C2-C6 end to end: script wrapper, abqmcp helpers, inputs/outputs, model_views with a list,
model_summary(only=...). Runs only with ABAQUS_E2E=1 (VM or native Windows, licence reachable).
Fixtures (FreeCAD): block_hole.step, 40 x 20 x 10 mm, through hole r 5 at (20, 10) along z;
two_blocks.step, two touching 20 x 20 x 10 blocks sharing x = 20."""
import json
import os
import struct
from pathlib import Path

import pytest

from abaqus_mcp.config import load
from abaqus_mcp.service import Service
from abaqus_mcp.transport import make
from conftest import FIX, e2e_project
from test_e2e_cantilever import call

pytestmark = pytest.mark.skipif(os.environ.get("ABAQUS_E2E") != "1", reason="set ABAQUS_E2E=1 (needs Abaqus: the VM or native Windows)")

JOB = "partition"

WRAPPER = '''from abaqus import mdb
from abaqusConstants import OFF
g = mdb.openStep("block_hole.step", scaleFromFile=OFF)
print("parts %d sum %d" % (g.numberOfParts, sum(x for x in range(4))))
raise ValueError("line six")
'''

BUILD = '''import json
from abaqus import mdb
from abaqusConstants import *
import abqmcp as h
two = h.import_solid("two_blocks.step", "Two")
p = h.import_solid("block_hole.step", "Blk")
out = {"two": h.check_part(two), "cut": h.cut(p, x=(15.0, 25.0, 100.0), y=(10.0,)), "plan": h.mesh_plan(p)}
del mdb.models["Model-1"].parts["Two"]
p.seedPart(size=2.0, deviationFactor=0.1, minSizeFactor=0.1)
edge = (0.0, 0.0, 2.5)
out["bias"] = h.seed_bias(p, [edge], (0.0, 0.0, 10.0), 0.3, 2.0)
p.generateMesh()
zs = sorted(n.coordinates[2] for n in p.edges.findAt(edge).getNodes())
out["spacing"] = [zs[1] - zs[0], zs[-1] - zs[-2]]
out["report"] = h.mesh_report(p)
p.Set(name="HOLE", faces=p.faces.findAt(((16.4645, 13.5355, 5.0),)))
p.Set(name="LEFT", faces=p.faces.findAt(((0.0, 5.0, 5.0),)))
mdb.saveAs(pathName="partition.cae")
with open("report.json", "w") as fh:
    json.dump(out, fh)
'''


def _run(tmp_path, name, text, **kw):
    s = tmp_path / name
    s.write_text(text)
    return call("run_script", job=JOB, script_path=str(s), **kw)


def test_wrapper_namespace_and_traceback(tmp_path):
    r = _run(tmp_path, "c3.py", WRAPPER, inputs=[str(FIX / "block_hole.step")])
    assert r["status"] == "error", r
    assert "parts 1 sum 6" in r["print_output"]
    assert 'File "c3.py", line 5' in r["traceback"] and r["error"] == "ValueError: line six"


def test_helpers_views_summary(tmp_path):
    r = _run(tmp_path, "build.py", BUILD, inputs=[str(FIX / "block_hole.step"), str(FIX / "two_blocks.step")],
             outputs=["report.json", "nothing.txt"])
    assert r["status"] == "ok", r
    assert r["missing"] == ["nothing.txt"] and "stderr" not in r
    rep = json.loads(Path(r["fetched"][0]).read_text())
    assert rep["two"]["valid"] and rep["two"]["cells"] == 2
    assert rep["cut"]["cells"] == 6 and len(rep["cut"]["skipped"]) == 1  # x = 100 is outside
    assert "TET" not in rep["plan"]["counts"] and rep["plan"]["non_hex"] == []
    first, last = rep["spacing"]
    assert last < first and first / last == pytest.approx(2.0 / 0.3, rel=0.2)  # fine end at z = 10
    assert rep["report"]["unmeshed_cells"] == 0

    s = call("model_summary", job=JOB, cae_file="partition.cae", only=["mesh"])
    assert set(s) == {"source", "model", "omitted", "status", "mesh"}, s
    assert s["mesh"]["nodes"] == rep["report"]["nodes"]
    assert s["mesh"]["techniques"] == {"Blk": {"HEX STRUCTURED": 6}}

    cfg = load()
    cfg.node_limit = 100
    svc = Service(cfg, make(cfg))
    svc.set_project(str(e2e_project()))
    assert "warning" in svc.model_summary(JOB, cae_file="partition.cae", only=["mesh"], live=False)["mesh"]

    v = call("model_views", job=JOB, cae_file="partition.cae", highlight=["HOLE", "LEFT"], live=False)
    assert v["status"] == "ok", v
    assert set(v["paths"]) == {"HOLE:iso", "LEFT:iso"}
    for p in v["paths"].values():
        head = Path(p).read_bytes()[:24]
        assert head[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", head[16:24]) == (900, 600)
