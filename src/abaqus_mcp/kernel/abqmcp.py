"""abaqus-mcp helpers for partitioned hex meshes, for `run_script` and `cae_live` scripts
(Abaqus/CAE kernel, Python 3.10): `import abqmcp as h`. Lengths are in the model's units.
Points are (x, y, z) tuples; a cell, face or edge is named by a point on it."""
import builtins
import math

from abaqus import mdb
from abaqusConstants import (DEFORMABLE_BODY, DELETE, ELEM_SHAPE, FREE, GEOMETRY, HEX, OFF, ON, SINGLE,
                             STRUCTURED, SWEEP, TECHNIQUE, TET, THREE_D, XYPLANE, XZPLANE, YZPLANE)
import assembly  # noqa: F401  (registers the assembly methods)
import mesh  # noqa: F401
import part  # noqa: F401  (registers mdb.openStep and the part methods)

sum = builtins.sum  # noqa: A001  `from abaqus import *` elsewhere shadows it


def _model(model=None):
    return mdb.models[model] if model else mdb.models[list(mdb.models.keys())[0]]


def _pt(v):
    return [round(float(c), 4) for c in v]


def check_part(p):
    """Validity and entity counts of a part."""
    return {"part": p.name, "valid": bool(p.geometryValidity), "cells": len(p.cells), "faces": len(p.faces),
            "edges": len(p.edges), "vertices": len(p.vertices)}


def import_solid(path, name="Part-1", model=None):
    """One 3D deformable part from a STEP file. A file with several bodies is imported one part per
    body and merged with InstanceFromBooleanMerge(keepIntersections=ON), which keeps the bodies as
    cells with shared faces (combine=ON leaves duplicate vertices). Raises ValueError with
    check_part() when the result is invalid."""
    m = _model(model)
    g = mdb.openStep(path, scaleFromFile=OFF)
    n = int(g.numberOfParts)
    kw = dict(geometryFile=g, combine=OFF, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    if n == 1:
        p = m.PartFromGeometryFile(name=name, **kw)
    else:
        a = m.rootAssembly
        tmp = ["%s_b%03d" % (name, i) for i in range(1, n + 1)]
        inst = [a.Instance(name=t + "-1", part=m.PartFromGeometryFile(name=t, bodyNum=i, **kw), dependent=ON)
                for i, t in enumerate(tmp, 1)]
        a.InstanceFromBooleanMerge(name=name, instances=tuple(inst), keepIntersections=ON,
                                   originalInstances=DELETE, domain=GEOMETRY)
        del a.instances[name + "-1"]
        for t in tmp:
            del m.parts[t]
        p = m.parts[name]
    info = check_part(p)
    info["bodies"] = n
    if not info["valid"]:
        raise ValueError("invalid geometry after import: %r" % info)
    return p


def _cells(p, cells):
    return p.cells if cells is None else p.cells.findAt(*[(tuple(c),) for c in cells])


def _basis(n):
    n = [float(c) for c in n]
    L = math.sqrt(sum(c * c for c in n))
    n = [c / L for c in n]
    a = [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0]
    u = [n[1] * a[2] - n[2] * a[1], n[2] * a[0] - n[0] * a[2], n[0] * a[1] - n[1] * a[0]]
    Lu = math.sqrt(sum(c * c for c in u))
    u = [c / Lu for c in u]
    v = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]]
    return u, v


def cut(p, x=(), y=(), z=(), planes=(), cells=None):
    """Partition cells by planes x = c, y = c, z = c and by (point, normal) planes. cells: points on
    the cells to cut (default all cells; re-read after every cut). A plane that cuts nothing is
    listed in `skipped`, not raised. Returns {"cells": n, "cuts": done, "skipped": [...]}."""
    todo = [("x", YZPLANE, c) for c in x] + [("y", XZPLANE, c) for c in y] + [("z", XYPLANE, c) for c in z]
    done, skipped = 0, []
    for axis, plane, c in todo:
        d = p.DatumPlaneByPrincipalPlane(principalPlane=plane, offset=float(c))
        try:
            p.PartitionCellByDatumPlane(datumPlane=p.datums[d.id], cells=_cells(p, cells))
            done += 1
        except Exception as e:  # noqa: BLE001  plane outside the cells or on an existing face
            skipped.append("%s=%g: %s" % (axis, c, str(e)[:80]))
    for pt, nrm in planes:
        u, v = _basis(nrm)
        q = [float(c) for c in pt]
        ids = [p.DatumPointByCoordinate(coords=tuple(q[i] + s * w[i] for i in range(3))).id
               for s, w in ((0.0, u), (1.0, u), (1.0, v))]
        d = p.DatumPlaneByThreePoints(point1=p.datums[ids[0]], point2=p.datums[ids[1]], point3=p.datums[ids[2]])
        try:
            p.PartitionCellByDatumPlane(datumPlane=p.datums[d.id], cells=_cells(p, cells))
            done += 1
        except Exception as e:  # noqa: BLE001
            skipped.append("plane %r n %r: %s" % (_pt(q), list(nrm), str(e)[:80]))
    return {"cells": len(p.cells), "cuts": done, "skipped": skipped}


def mesh_plan(p, prefer=(STRUCTURED, SWEEP), tet=True):
    """Per cell: hex with the first technique of `prefer` that Abaqus accepts, else tet FREE
    (tet=False: left as it was). Returns {"counts": {technique: n}, "non_hex": [point, ...]}."""
    counts, non_hex = {}, []
    for c in p.cells:
        reg = p.cells.findAt((c.pointOn[0],))
        got = None
        for t in prefer:
            try:
                p.setMeshControls(regions=reg, elemShape=HEX, technique=t)
                got = str(t)
                break
            except Exception:  # noqa: BLE001  "Some regions cannot be Mapped." and similar
                pass
        if got is None:
            non_hex.append(_pt(c.pointOn[0]))
            if tet:
                p.setMeshControls(regions=reg, elemShape=TET, technique=FREE)
                got = "TET"
            else:
                got = "none"
        counts[got] = counts.get(got, 0) + 1
    return {"counts": counts, "non_hex": non_hex}


def seed_bias(p, edges, fine, min_size, max_size):
    """Single-bias seeds on the edges through the given points: min_size at the end nearer the
    point `fine`, max_size at the other. Returns {"end1": n, "end2": n}."""
    f = [float(c) for c in fine]
    e1, e2 = [], []
    for q in edges:
        e = p.edges.findAt(tuple(q))
        v0, v1 = (p.vertices[i].pointOn[0] for i in e.getVertices()[:2])
        d0, d1 = (sum((a - b) ** 2 for a, b in zip(v, f)) for v in (v0, v1))
        (e1 if d0 <= d1 else e2).append((tuple(q),))  # end1: fine at the first vertex
    kw = {}
    if e1:
        kw["end1Edges"] = p.edges.findAt(*e1)
    if e2:
        kw["end2Edges"] = p.edges.findAt(*e2)
    if kw:
        p.seedEdgeByBias(biasMethod=SINGLE, minSize=float(min_size), maxSize=float(max_size), **kw)
    return {"end1": len(e1), "end2": len(e2)}


def mesh_report(p, node_limit=250000):
    """Nodes, elements by type, cells by assigned technique, unmeshed cells, Abaqus quality checks,
    and a warning above node_limit (Teaching Edition: 250 000; 0 turns it off)."""
    types, tech = {}, {}
    for el in p.elements:
        types[str(el.type)] = types.get(str(el.type), 0) + 1
    for c in p.cells:
        k = "%s %s" % (p.getMeshControl(region=c, attribute=ELEM_SHAPE),
                       p.getMeshControl(region=c, attribute=TECHNIQUE))
        tech[k] = tech.get(k, 0) + 1
    try:
        unmeshed = len(p.getUnmeshedRegions().cells)
    except Exception:  # noqa: BLE001  raises or returns None when every cell is meshed
        unmeshed = 0
    out = {"part": p.name, "nodes": len(p.nodes), "elements": len(p.elements), "types": types,
           "techniques": tech, "unmeshed_cells": unmeshed}
    if len(p.elements):
        from abaqusConstants import ANALYSIS_CHECKS
        q = p.verifyMeshQuality(criterion=ANALYSIS_CHECKS)
        out["quality"] = {"failed": len(q["failedElements"]), "warning": len(q["warningElements"])}
    if node_limit and len(p.nodes) > node_limit:
        out["warning"] = "%d nodes > node limit %d" % (len(p.nodes), node_limit)
    return out
