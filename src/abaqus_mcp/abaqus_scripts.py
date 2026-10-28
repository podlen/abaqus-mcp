"""Scripts that run inside Abaqus Python (3.10 in Abaqus 2026, SMApy/python3.10).

Large results (odb_query, model_info) are written to a JSON file in the job directory
(P["result"]) and fetched by the server; small ones print one JSON document between
markers. Pattern adapted from MOBAI547800/abaqus-mcp-server odb_script_templates.py (MIT), see
NOTICE: a generated script prints one JSON document between markers, so banner text on
stdout cannot corrupt it. Parameters are embedded as a JSON string literal.
"""
from __future__ import annotations

import json

START, END = "===JSON_START===", "===JSON_END==="

_HEAD = '''import json, os, sys
P = json.loads({params})
def _num(x):
    try:
        return [float(v) for v in x] if hasattr(x, "__len__") else float(x)
    except Exception:
        return str(x)
def _emit(d):
    if P.get("result"):
        with open(P["result"], "w") as fh:
            json.dump(d, fh)
        return
    print("%s")
    print(json.dumps(d))
    print("%s")
''' % ("{start}", "{end}")


def _build(body: str, params: dict) -> str:
    head = _HEAD.replace("{start}", START).replace("{end}", END)
    return head.replace("{params}", json.dumps(json.dumps(params))) + body


_ODB_QUERY = '''
from odbAccess import openOdb
odb = openOdb(P["odb"], readOnly=True)
try:
    if P["step"] not in odb.steps.keys():
        _emit({"error": "step not found", "steps": list(odb.steps.keys())}); sys.exit(0)
    step = odb.steps[P["step"]]
    frames = [{"index": i, "description": f.description,
               "frequency": _num(f.frequency) if hasattr(f, "frequency") and f.frequency is not None else None}
              for i, f in enumerate(step.frames[:50])]
    out = {"step": P["step"], "n_frames": len(step.frames), "frames": frames}
    if P["variable"]:
        fi = P["frame"] + len(step.frames) if P["frame"] < 0 else P["frame"]
        frame = step.frames[fi]
        if P["variable"] not in frame.fieldOutputs.keys():
            _emit({"error": "variable not found", "available": list(frame.fieldOutputs.keys())}); sys.exit(0)
        fo = frame.fieldOutputs[P["variable"]]
        if P["set"]:
            name = P["set"].upper()
            region = None
            for coll in ("nodeSets", "elementSets"):
                c = getattr(odb.rootAssembly, coll)
                if name in c.keys():
                    region = c[name]
            if region is None:
                for inst in odb.rootAssembly.instances.values():
                    for coll in ("nodeSets", "elementSets"):
                        c = getattr(inst, coll)
                        if name in c.keys():
                            region = c[name]
            if region is None:
                _emit({"error": "set not found: " + P["set"]}); sys.exit(0)
            fo = fo.getSubset(region=region)
        idx = None
        if P["component"]:
            idx = list(fo.componentLabels).index(P["component"])
        rows = []
        for v in fo.values[:P["max_values"]]:
            label = v.nodeLabel if v.nodeLabel is not None else v.elementLabel
            d = _num(v.data)
            rows.append({"label": label, "data": d if idx is None or not isinstance(d, list) else d[idx]})
        out.update(frame=fi, frame_description=frame.description, variable=P["variable"],
                   component=P["component"], set=P["set"], n_values=len(fo.values), values=rows)
    _emit(out)
finally:
    odb.close()
'''

_MODEL_INFO = '''
from abaqus import *
from abaqusConstants import *
mdb = openMdb(pathName=P["cae"])
models = {}
for mname, m in mdb.models.items():
    parts = {}
    for pn, p in m.parts.items():
        parts[pn] = {"nodes": len(p.nodes), "elements": len(p.elements),
                     "node_sets": list(p.sets.keys())}
    mats = {}
    for mn, mat in m.materials.items():
        mats[mn] = {"elastic": _num(mat.elastic.table[0]) if hasattr(mat, "elastic") and mat.elastic else None,
                    "density": _num(mat.density.table[0]) if hasattr(mat, "density") and mat.density else None}
    steps = {sn: {"type": s.__class__.__name__, "nlgeom": getattr(s, "nlgeom", None) == ON} for sn, s in m.steps.items()}
    models[mname] = {"parts": parts, "assembly_sets": list(m.rootAssembly.sets.keys()),
                     "steps": steps, "materials": mats}
_emit({"models": models})
'''

_WRITE_INP = '''
from abaqus import *
from abaqusConstants import *
mdb = openMdb(pathName=P["cae"])
j = mdb.Job(name=P["job"], model=P["model"])
j.writeInput(consistencyChecking=OFF)
_emit({"inp": P["job"] + ".inp"})
'''

# No dot in the printToFile name (the file is silently not written) and no maximize()
# under noGUI; see docs/prior-art.md.
_VIEWPORT = '''
from abaqus import *
from abaqusConstants import *
odb = session.openOdb(name=P["odb"], readOnly=True)
vp = session.viewports["Viewport: 1"]
vp.setValues(displayedObject=odb)
sname = list(odb.steps.keys())[P["step_index"]]
nfr = len(odb.steps[sname].frames)
fi = P["frame"] + nfr if P["frame"] < 0 else P["frame"]
if P["variable"]:
    vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
    if P["invariant"]:
        ref = (INVARIANT, P["invariant"])
    elif P["component"]:
        ref = (COMPONENT, P["component"])
    else:  # default per field type: scalar none, vector magnitude, tensor Mises
        ftype = str(odb.steps[sname].frames[fi].fieldOutputs[P["variable"]].type)
        ref = (INVARIANT, "Mises") if "TENSOR" in ftype else (INVARIANT, "Magnitude") if "VECTOR" in ftype else None
    kw = dict(variableLabel=P["variable"], outputPosition=NODAL)
    if ref:
        kw["refinement"] = ref
    vp.odbDisplay.setPrimaryVariable(**kw)
else:
    vp.odbDisplay.display.setValues(plotState=(DEFORMED,))
vp.odbDisplay.setFrame(step=P["step_index"], frame=fi)
session.pngOptions.setValues(imageSize=(P["width"], P["height"]))
session.printOptions.setValues(vpDecorations=OFF)
session.printToFile(fileName=P["out"], format=PNG, canvasObjects=(vp,))
ok = os.path.exists(P["out"] + ".png")
_emit({"ok": ok, "file": P["out"] + ".png"})
'''


def odb_query(odb, step, frame=-1, variable=None, set_name=None, component=None, max_values=1000,
              result=None) -> str:
    return _build(_ODB_QUERY, dict(odb=odb, step=step, frame=frame, variable=variable,
                                   set=set_name, component=component, max_values=max_values,
                                   result=result))


def model_info(cae, result=None) -> str:
    return _build(_MODEL_INFO, dict(cae=cae, result=result))


def write_inp(cae, model, job) -> str:
    return _build(_WRITE_INP, dict(cae=cae, model=model, job=job))


def viewport(odb, out, step_index=0, frame=-1, variable="U", invariant=None,
             component=None, width=1200, height=800) -> str:
    return _build(_VIEWPORT, dict(odb=odb, out=out, step_index=step_index, frame=frame,
                                  variable=variable, invariant=invariant, component=component,
                                  width=width, height=height))
