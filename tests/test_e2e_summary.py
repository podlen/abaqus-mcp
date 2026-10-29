"""C3 saved-file half end to end: model_summary and model_views on a .cae built by
tests/summary_model_build.py (known contents). Runs only with ABAQUS_E2E=1."""
import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from test_e2e_cantilever import call

pytestmark = pytest.mark.skipif(os.environ.get("ABAQUS_E2E") != "1", reason="set ABAQUS_E2E=1 (needs VM + Abaqus)")

HERE = Path(__file__).parent
SCHEMA = json.loads((HERE.parent / "docs" / "model_summary.schema.json").read_text())
JOB, CAE = "summary-test", "summary_test.cae"

# Known by construction (tests/summary_model_build.py). Billet cylinder: one cell, three faces, two
# edges, two vertices (seam-less circles); Axi 4 x 4 CAX4R: 25 nodes, 16 elements.
EXPECTED = {
    "source": CAE,
    "model": "Model-1",
    "models": ["Model-1", "Solid"],
    "omitted": {},
    "parts": {
        "Axi": {"dim": "AXI", "type": "DEFORMABLE_BODY", "cells": 0, "faces": 1, "edges": 4, "vertices": 4,
                "bbox": [0.0, 0.0, 0.0, 10.0, 10.0, 0.0], "features": ["Shell planar-1"],
                "sets": {"ALL": {"faces": 1, "nodes": 25, "elems": 16}},
                "surfaces": {"TOPS": {"edges": 1, "nodes": 5, "elems": 4}}},
        "Billet": {"dim": "3D", "type": "DEFORMABLE_BODY", "cells": 1, "faces": 3, "edges": 2, "vertices": 2,
                   "bbox": [-10.0, -10.0, 0.0, 10.0, 10.0, 20.0], "features": ["Solid extrude-1"],
                   "edge_radii": [10.0], "face_radii": [10.0],
                   "sets": {"TOPFACE": {"faces": 1}}, "surfaces": {}},
        "Plate": {"dim": "AXI", "type": "ANALYTIC_RIGID_SURFACE", "cells": 0, "faces": 0, "edges": 1, "vertices": 2,
                  "bbox": [0.0, 10.0, 0.0, 12.0, 10.0, 0.0], "features": ["2D Analytic rigid shell-1", "RP"],
                  "sets": {}, "surfaces": {"FACE": {"edges": 1}}},
    },
    "instances": {"Axi-1": {"part": "Axi", "dependent": True, "bbox": [0.0, 0.0, 0.0, 10.0, 10.0, 0.0]},
                  "Plate-1": {"part": "Plate", "dependent": True, "bbox": [0.0, 10.0, 0.0, 12.0, 10.0, 0.0]}},
    "sets": {"SYM": {"edges": 1, "nodes": 5, "elems": 4}, "RP": {"nodes": 1}},
    "surfaces": {"PLATE_S": {"edges": 1}, "TOP_AXI": {"edges": 1, "nodes": 5, "elems": 4}},
    "materials": {"Steel": {"elastic": {"type": "ISOTROPIC", "table": [[210000.0, 0.3]]},
                            "plastic": {"hardening": "ISOTROPIC", "table": [[250.0, 0.0], [300.0, 0.1]]},
                            "density": [[7.85e-09]]}},
    "sections": {"Sec": {"type": "HomogeneousSolidSection", "material": "Steel"}},
    "assignments": [{"part": "Axi", "section": "Sec", "region": "ALL"}],
    "steps": [
        {"name": "Initial", "procedure": "InitialStep", "nlgeom": False},
        {"name": "Upset", "procedure": "StaticStep", "nlgeom": True, "time_period": 1.0, "initial_inc": 0.01,
         "min_inc": 1e-06, "max_inc": 0.1, "max_num_inc": 500, "inc_method": "AUTOMATIC"}],
    "loads": [{"name": "Push", "type": "ConcentratedForce", "step": "Upset", "region": "RP", "values": {"cf2": -1000.0}}],
    "bcs": [{"name": "Symm", "type": "DisplacementBC", "step": "Initial", "region": "SYM", "values": {"u2": 0.0}}],
    "interactions": [{"name": "Cont", "type": "SurfaceToSurfaceStd", "step": "Upset", "prop": "fric",
                      "discretization": "SURFACE_TO_SURFACE", "sliding": "FINITE",
                      "main": "PLATE_S", "secondary": "TOP_AXI"}],
    "contact_props": {"fric": {"friction": [0.1], "normal": "HARD"}},
    "mesh": {"nodes": 25, "elems": 16, "types": {"CAX4R": 16}, "unmeshed": ["Billet"],
             "techniques": {"Axi": {"QUAD_DOMINATED FREE": 1}, "Billet": {"HEX SWEEP": 1}}},
}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    script = tmp_path_factory.mktemp("b") / "build.py"
    script.write_text((HERE / "summary_model_build.py").read_text())
    r = call("run_script", job=JOB, script_path=str(script))
    assert r["status"] == "ok", r
    return r


def test_model_summary_matches_known_contents(built):
    r = call("model_summary", job=JOB, cae_file=CAE)
    assert r.pop("status") == "ok", r
    Draft202012Validator(SCHEMA).validate(r)
    assert set(r) == set(SCHEMA["properties"])
    for k, v in EXPECTED.items():
        assert r[k] == v, k
    assert len(json.dumps(r)) < 20000
    print("summary bytes:", len(json.dumps(r)))


def test_model_summary_second_model_independent_instance(built):
    r = call("model_summary", job=JOB, cae_file=CAE, model="Solid")
    assert r.pop("status") == "ok", r
    Draft202012Validator(SCHEMA).validate(r)
    assert r["model"] == "Solid" and r["instances"] == {
        "Block-1": {"part": "Block", "dependent": False, "translation": [5.0, 0.0, 3.0], "bbox": [5.0, 0.0, 3.0, 7.0, 2.0, 5.0]}}
    assert r["parts"]["Block"]["dim"] == "3D" and r["parts"]["Block"]["cells"] == 1
    assert r["mesh"] == {"nodes": 27, "elems": 8, "types": {"C3D8R": 8}, "unmeshed": [],
                         "techniques": {"Block": {"HEX STRUCTURED": 1}}}


def _pngs(r):
    assert r["status"] == "ok", r
    assert set(r["paths"]) == {"iso", "front", "top"}
    for p in r["paths"].values():
        assert os.path.getsize(p) > 0
        print("png:", p)


def test_model_views(built):
    _pngs(call("model_views", job=JOB, cae_file=CAE))


def test_model_views_highlight_surface_and_set(built):
    _pngs(call("model_views", job=JOB, cae_file=CAE, highlight="TOP_AXI"))
    _pngs(call("model_views", job=JOB, cae_file=CAE, highlight="SYM"))
    assert call("model_views", job=JOB, cae_file=CAE, highlight="NOPE")["status"] == "error"
