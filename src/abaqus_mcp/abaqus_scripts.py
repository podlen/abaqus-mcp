"""Scripts that run inside Abaqus Python (3.10 in Abaqus 2026, SMApy/python3.10).

Large results (odb_query, model_summary) are written to a JSON file in the job directory
(P["result"]) and fetched by the server; small ones print one JSON document between
markers. Pattern adapted from MOBAI547800/abaqus-mcp-server odb_script_templates.py (MIT), see
NOTICE: a generated script prints one JSON document between markers, so banner text on
stdout cannot corrupt it. Parameters are embedded as a JSON string literal.
"""
from __future__ import annotations

import json
from pathlib import Path

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
    # print() and sys.stderr go to abaqus.rpy under cae noGUI; only sys.__stdout__ reaches stdout
    sys.__stdout__.write("%s\\n" + json.dumps(d) + "\\n%s\\n")
    sys.__stdout__.flush()
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
              for i, f in ((i, step.frames[i]) for i in range(min(50, len(step.frames))))]
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
        for v in [fo.values[i] for i in range(min(P["max_values"], len(fo.values)))]:
            label = v.nodeLabel if v.nodeLabel is not None else v.elementLabel
            d = _num(v.data)
            rows.append({"label": label, "data": d if idx is None or not isinstance(d, list) else d[idx]})
        out.update(frame=fi, frame_description=frame.description, variable=P["variable"],
                   component=P["component"], set=P["set"], n_values=len(fo.values), values=rows)
    _emit(out)
finally:
    odb.close()
'''

_ODB_HISTORY = '''
from odbAccess import openOdb
def _cut(pts, n):
    if len(pts) <= n:
        return pts
    keep = {0, len(pts) - 1, min(range(len(pts)), key=lambda i: pts[i][1]), max(range(len(pts)), key=lambda i: pts[i][1])}
    rest = [i for i in range(len(pts)) if i not in keep]
    k = n - len(keep)
    keep.update(rest[int(j * len(rest) / k)] for j in range(k))
    return [pts[i] for i in sorted(keep)]
odb = openOdb(P["odb"], readOnly=True)
try:
    names = list(odb.steps.keys())
    if P["step"] and P["step"] not in names:
        _emit({"error": "step not found", "steps": names}); sys.exit(0)
    use = [P["step"]] if P["step"] else names
    if not P["outputs"]:
        listing = {}
        for sn in use:
            listing[sn] = dict((r.name, sorted(r.historyOutputs.keys())) for r in odb.steps[sn].historyRegions.values())
        _emit({"steps": listing}); sys.exit(0)
    want = [o.upper() for o in P["outputs"]]
    out = {}
    for sn in use:
        for r in odb.steps[sn].historyRegions.values():
            if P["region"] and P["region"].lower() not in r.name.lower():
                continue
            for o, ho in r.historyOutputs.items():
                if o.upper() in want:
                    out.setdefault(r.name + " / " + o, []).extend([float(t), float(v)] for t, v in ho.data)
    res = {}
    for k, pts in out.items():
        res[k] = {"n_points": len(pts), "points": _cut(pts, P["max_points"])}
    _emit({"step": P["step"], "series": res} if res else {"error": "no matching history output; call without outputs to list them"})
finally:
    odb.close()
'''

_SUMMARY_CALL = '''
from abaqus import *
from abaqusConstants import *
mdb = openMdb(pathName=P["cae"])
_emit(model_summary(mdb, P["model"], P["source"]))
'''

_VIEWS_CALL = '''
from abaqus import *
from abaqusConstants import *
from caeModules import *
mdb = openMdb(pathName=P["cae"])
_emit(dict(render_views(mdb, session, session.viewports["Viewport: 1"], P["model"], P["base"], P["highlight"],
                        P["views"], P["size"]), ok=True))
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
from caeModules import *  # registers the visualization module; without it displayedObject rejects an Odb
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


def _kernel(name: str) -> str:
    return (Path(__file__).parent / "kernel" / name).read_text()


def model_summary(cae, model=None, source=None, result=None) -> str:
    return _build(_kernel("summary.py") + _SUMMARY_CALL,
                  dict(cae=cae, model=model, source=source or cae, result=result))


def model_views(cae, base, model=None, highlight=None, views=("iso", "front", "top"), size=(900, 600)) -> str:
    return _build(_kernel("views.py") + _VIEWS_CALL,
                  dict(cae=cae, model=model, base=base, highlight=highlight, views=list(views), size=list(size)))


def write_inp(cae, model, job) -> str:
    return _build(_WRITE_INP, dict(cae=cae, model=model, job=job))


def viewport(odb, out, step_index=0, frame=-1, variable="U", invariant=None,
             component=None, width=1200, height=800) -> str:
    return _build(_VIEWPORT, dict(odb=odb, out=out, step_index=step_index, frame=frame,
                                  variable=variable, invariant=invariant, component=component,
                                  width=width, height=height))


def odb_history(odb, step=None, region=None, outputs=None, max_points=200, result=None) -> str:
    return _build(_ODB_HISTORY, dict(odb=odb, step=step, region=region, outputs=outputs,
                                     max_points=max_points, result=result))


# -- live CAE session: scripts run by mcp_live_kernel.run (mdb, session in scope; `result` is returned)
_LIVE_SUMMARY = """
result = model_summary(mdb, {model!r}, "live")
"""

_LIVE_VIEWS = """
import os
os.makedirs(os.path.dirname({base!r}), exist_ok=True)
_vp = session.viewports[session.currentViewportName]
_old = _vp.displayedObject
try:
    result = render_views(mdb, session, _vp, {model!r}, {base!r}, {highlight!r}, {views!r}, {size!r})
finally:
    try:
        _vp.setValues(displayedObject=_old)
    except Exception:
        pass
"""


def live_summary(model=None) -> str:
    return _kernel("summary.py") + _LIVE_SUMMARY.format(model=model)


def live_views(base, model=None, highlight=None, views=("iso", "front", "top"), size=(900, 600)) -> str:
    return _kernel("views.py") + _LIVE_VIEWS.format(base=base, model=model, highlight=highlight,
                                                    views=list(views), size=tuple(size))
