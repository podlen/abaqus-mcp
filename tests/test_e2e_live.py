"""Live bridge end to end through the MCP tools: needs an open Abaqus/CAE window with the mcp_live
plug-in loaded (setup-windows.cmd or ./setup.sh live). Runs only with ABAQUS_LIVE=1."""
import os

import pytest

from conftest import e2e_project
from test_e2e_cantilever import call

pytestmark = pytest.mark.skipif(os.environ.get("ABAQUS_LIVE") != "1", reason="set ABAQUS_LIVE=1 (needs an open CAE window)")

BLOCK = '''
s = mdb.models['Model-1'].ConstrainedSketch(name='live_s', sheetSize=1.0)
s.rectangle(point1=(0.0, 0.0), point2=(0.1, 0.05))
p = mdb.models['Model-1'].Part(name='LiveBlock', dimensionality=THREE_D, type=DEFORMABLE_BODY)
p.BaseSolidExtrude(sketch=s, depth=0.02)
print('made', p.name)
result = {'parts': sorted(mdb.models['Model-1'].parts.keys()), 'cells': len(p.cells)}
'''


def test_cae_live_edits_open_model():
    r = call("cae_live", script=BLOCK, timeout=120)
    assert r["status"] == "ok", r
    assert "made LiveBlock" in r["output"]
    assert "LiveBlock" in r["result"]["parts"] and r["result"]["cells"] == 1

    s = call("model_summary", job="live")
    assert s["status"] == "ok" and s.get("source") == "live", s
    assert s["parts"]["LiveBlock"]["cells"] == 1

    v = call("model_views", job="live")
    assert v["status"] == "ok", v
    assert all(os.path.getsize(p) > 0 and p.startswith(str(e2e_project())) for p in v["paths"].values())


def test_cae_live_traceback():
    r = call("cae_live", script="raise ValueError('deliberate')")
    assert r["status"] == "error" and "ValueError: deliberate" in r["traceback"]
