"""abaqus-mcp helpers for partitioned hex meshes, for `run_script` and `cae_live` scripts
(Abaqus/CAE kernel, Python 3.10): `import abqmcp as h`. Lengths are in the model's units.
Points are (x, y, z) tuples; a cell, face or edge is named by a point on it."""
import builtins
import math

from abaqus import mdb
from abaqusConstants import (DEFORMABLE_BODY, DELETE, ELEM_SHAPE, FREE, GEOMETRY, HEX, LEFT, OFF, ON, RIGHT,
                             SINGLE, STRUCTURED, SWEEP, TECHNIQUE, TET, THREE_D, XYPLANE, XZPLANE, YZPLANE)
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


def _cells(p, cells, box=None):
    if box is not None:
        b = [float(c) for c in box]
        got = p.cells.getByBoundingBox(xMin=b[0], yMin=b[1], zMin=b[2], xMax=b[3], yMax=b[4], zMax=b[5])
        if not len(got):
            raise ValueError("no cell lies wholly inside box %r" % (b,))
        return got
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


def cut(p, x=(), y=(), z=(), planes=(), cells=None, box=None):
    """Partition cells by planes x = c, y = c, z = c and by (point, normal) planes. Only the cells
    lying wholly inside box = (xmin, ymin, zmin, xmax, ymax, zmax), or the cells through the points
    `cells`, are cut (default all cells; the selection is re-read after every cut), so a plane for one
    zone leaves the rest of the part alone. A plane that cuts nothing is listed in `skipped`.
    Returns {"cells": n, "cuts": done, "skipped": [...]}."""
    todo = [("x", YZPLANE, c) for c in x] + [("y", XZPLANE, c) for c in y] + [("z", XYPLANE, c) for c in z]
    done, skipped = 0, []
    for axis, plane, c in todo:
        d = p.DatumPlaneByPrincipalPlane(principalPlane=plane, offset=float(c))
        try:
            p.PartitionCellByDatumPlane(datumPlane=p.datums[d.id], cells=_cells(p, cells, box))
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
            p.PartitionCellByDatumPlane(datumPlane=p.datums[d.id], cells=_cells(p, cells, box))
            done += 1
        except Exception as e:  # noqa: BLE001
            skipped.append("plane %r n %r: %s" % (_pt(q), list(nrm), str(e)[:80]))
    return {"cells": len(p.cells), "cuts": done, "skipped": skipped}


def _free(m, base):
    """A name not yet used by a part or an assembly instance."""
    taken = set(m.parts.keys()) | set(m.rootAssembly.instances.keys()) | set(m.sketches.keys())
    name, i = base, 1
    while name in taken or name + "-1" in taken:
        name, i = "%s_%d" % (base, i), i + 1
    return name


def _extrude(m, base, sketch, depth):
    """Instance of a new part extruded from sketch over local z 0..depth."""
    c = m.Part(name=_free(m, base), dimensionality=THREE_D, type=DEFORMABLE_BODY)
    c.BaseSolidExtrude(sketch=sketch, depth=float(depth))
    return m.rootAssembly.Instance(name=c.name + "-1", part=c, dependent=ON)


def prism(p, face, span, offset=0.0, name="Prism", model=None):
    """Solid prism from the outline of a planar face of p (a point on it; normal along x, y or z; one
    loop of lines and circular arcs): the outline offset inward by `offset` (negative: outward),
    extruded over span = (a, b) along the face normal. Returns an assembly instance in p's frame,
    for imprint()."""
    m = _model(model)
    a = m.rootAssembly
    f = p.faces.findAt((tuple(float(c) for c in face),))[0]
    n = [abs(c) for c in f.getNormal()]
    k = n.index(max(n))
    if max(n) < 1 - 1e-9:
        raise ValueError("face normal %r is not along x, y or z" % (_pt(f.getNormal()),))
    u, v = (k + 1) % 3, (k + 2) % 3  # sketch axes; local z maps to axis k

    def uv(q):
        return (q[u], q[v])

    def outline(tag):
        s = m.ConstrainedSketch(name=_free(m, name + tag), sheetSize=1000.0)
        for ei in f.getEdges():
            e = p.edges[ei]
            vs = e.getVertices()
            if len(vs) != 2:
                raise ValueError("closed edge at %r in the outline" % (_pt(e.pointOn[0]),))
            q0, q1 = (p.vertices[i].pointOn[0] for i in vs)
            q = e.pointOn[0]
            try:
                e.getRadius()
                s.Arc3Points(point1=uv(q0), point2=uv(q1), point3=uv(q))
            except Exception:  # noqa: BLE001  not a circular edge
                d = [uv(q1)[i] - uv(q0)[i] for i in (0, 1)]
                w = [uv(q)[i] - uv(q0)[i] for i in (0, 1)]
                if abs(d[0] * w[1] - d[1] * w[0]) > 1e-6 * (d[0] ** 2 + d[1] ** 2):
                    raise ValueError("edge at %r is neither a line nor an arc" % (_pt(q),))
                s.Line(point1=uv(q0), point2=uv(q1))
        return s

    depth = float(span[1]) - float(span[0])
    if not offset:
        inst = _extrude(m, name, outline(""), depth)
    else:
        full = f.getSize(printResults=False) * depth
        inst, errors = None, []
        for side in (LEFT, RIGHT):
            try:
                s = outline("_%s" % side)
                orig = tuple(s.geometry.values())
                s.offset(distance=abs(float(offset)), objectList=orig, side=side)
                s.delete(objectList=orig)
                i = _extrude(m, name, s, depth)
            except Exception as e:  # noqa: BLE001
                errors.append(str(e)[:80])
                continue
            if (m.parts[i.partName].getVolume() < full) == (offset > 0):
                inst = i
                break
            pn = i.partName
            del a.instances[i.name]
            del m.parts[pn]
        if inst is None:
            raise ValueError("offset %g of the outline failed: %r" % (offset, errors))
    if k != 2:  # cyclic axis permutation: local (x, y, z) -> axes (u, v, k)
        a.rotate(instanceList=(inst.name,), axisPoint=(0.0, 0.0, 0.0), axisDirection=(1.0, 1.0, 1.0),
                 angle=120.0 * (k + 1))
    shift = [0.0, 0.0, 0.0]
    shift[k] = float(span[0])
    a.translate(instanceList=(inst.name,), vector=tuple(shift))
    return inst


def tool_box(lo, hi, name="Box", model=None):
    """Box from corner lo = (xmin, ymin, zmin) to hi = (xmax, ymax, zmax), as an assembly instance."""
    m = _model(model)
    s = m.ConstrainedSketch(name=_free(m, name), sheetSize=1000.0)
    s.rectangle(point1=(float(lo[0]), float(lo[1])), point2=(float(hi[0]), float(hi[1])))
    inst = _extrude(m, name, s, float(hi[2]) - float(lo[2]))
    m.rootAssembly.translate(instanceList=(inst.name,), vector=(0.0, 0.0, float(lo[2])))
    return inst


def tool_cylinder(p0, p1, r, name="Cyl", model=None):
    """Cylinder of radius r with its axis from point p0 to point p1, as an assembly instance."""
    m = _model(model)
    a = m.rootAssembly
    d = [float(q) - float(o) for o, q in zip(p0, p1)]
    L = math.sqrt(sum(c * c for c in d))
    s = m.ConstrainedSketch(name=_free(m, name), sheetSize=1000.0)
    s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(float(r), 0.0))
    inst = _extrude(m, name, s, L)
    d = [c / L for c in d]
    ax = (-d[1], d[0], 0.0)  # z x d
    if math.hypot(ax[0], ax[1]) > 1e-12:
        a.rotate(instanceList=(inst.name,), axisPoint=(0.0, 0.0, 0.0), axisDirection=ax,
                 angle=math.degrees(math.acos(max(-1.0, min(1.0, d[2])))))
    elif d[2] < 0:
        a.rotate(instanceList=(inst.name,), axisPoint=(0.0, 0.0, 0.0), axisDirection=(1.0, 0.0, 0.0), angle=180.0)
    a.translate(instanceList=(inst.name,), vector=tuple(float(c) for c in p0))
    return inst


def imprint(p, region, minus=(), sets=("REGION", "REST"), min_volume=0.0, name=None, model=None):
    """Split p into cells along the boundary of a solid region: `region` minus the `minus` solids
    (assembly instances in p's frame from prism, tool_box, tool_cylinder) is merged into p with
    InstanceFromBooleanMerge(keepIntersections=ON). The region must lie inside p. The merged part
    replaces p (or is called `name`) and gets part sets sets[0] (region cells of at least min_volume)
    and sets[1] (the rest); tool parts are deleted. Region cells are told apart by volume.
    Returns check_part() plus the cell volumes per set and the volume mismatch."""
    m = _model(model)
    a = m.rootAssembly
    tmp = [i.partName for i in (region,) + tuple(minus)]
    if minus:
        cut_name = _free(m, p.name + "_region")
        a.InstanceFromBooleanCut(name=cut_name, instanceToBeCut=region, cuttingInstances=tuple(minus),
                                 originalInstances=DELETE)
        region = a.instances[cut_name + "-1"]
        tmp.append(cut_name)
    rp = m.parts[region.partName]
    vr = [rp.getVolume(cells=rp.cells[i:i + 1]) for i in range(len(rp.cells))]
    v0 = p.getVolume()
    new = _free(m, (name or p.name) + "_imprint")
    body = a.Instance(name=_free(m, p.name + "_body") + "-1", part=p, dependent=ON)
    a.InstanceFromBooleanMerge(name=new, instances=(body, region), keepIntersections=ON,
                               originalInstances=DELETE, domain=GEOMETRY)
    del a.instances[new + "-1"]
    for t in set(tmp):
        del m.parts[t]
    k = m.parts[new]
    vm = [k.getVolume(cells=k.cells[i:i + 1]) for i in range(len(k.cells))]
    if abs(sum(vm) - v0) > 1e-6 * v0:
        raise ValueError("region sticks out of the part: volume %g -> %g" % (v0, sum(vm)))
    free, reg, mis = list(range(len(vm))), [], 0.0
    for v in sorted(vr, reverse=True):
        j = min(free, key=lambda i: abs(vm[i] - v))
        mis = max(mis, abs(vm[j] - v) / v)
        free.remove(j)
        if v >= min_volume:
            reg.append(j)
    if mis > 1e-4:
        raise ValueError("region cells do not match merged cells by volume (mismatch %.2g)" % mis)
    rest = [i for i in range(len(vm)) if i not in reg]
    for set_name, ids in zip(sets, (reg, rest)):
        if ids:
            k.Set(name=set_name, cells=sum((k.cells[i:i + 1] for i in ids[1:]), k.cells[ids[0]:ids[0] + 1]))
    if name is None or name == p.name:
        old = p.name
        del m.parts[old]
        m.parts.changeKey(fromName=new, toName=old)
        k = m.parts[old]
    elif name != new:
        m.parts.changeKey(fromName=new, toName=name)
        k = m.parts[name]
    out = check_part(k)
    out.update({sets[0]: sorted(round(vm[i], 3) for i in reg), sets[1]: sorted(round(vm[i], 3) for i in rest),
                "mismatch": mis})
    return out


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
    """Nodes, elements by type, cells by assigned technique, unmeshed cells (count and a point on
    each of the first 20), Abaqus quality checks, and a warning above node_limit (Teaching Edition:
    250 000; 0 turns it off)."""
    types, tech = {}, {}
    for el in p.elements:
        types[str(el.type)] = types.get(str(el.type), 0) + 1
    for c in p.cells:
        k = "%s %s" % (p.getMeshControl(region=c, attribute=ELEM_SHAPE),
                       p.getMeshControl(region=c, attribute=TECHNIQUE))
        tech[k] = tech.get(k, 0) + 1
    unmeshed = [_pt(c.pointOn[0]) for c in p.cells if not c.getElements()]  # None when unmeshed
    out = {"part": p.name, "nodes": len(p.nodes), "elements": len(p.elements), "types": types,
           "techniques": tech, "unmeshed_cells": len(unmeshed), "unmeshed_at": unmeshed[:20]}
    if len(p.elements):
        from abaqusConstants import ANALYSIS_CHECKS
        q = p.verifyMeshQuality(criterion=ANALYSIS_CHECKS)
        out["quality"] = {"failed": len(q["failedElements"]), "warning": len(q["warningElements"])}
    if node_limit and len(p.nodes) > node_limit:
        out["warning"] = "%d nodes > node limit %d" % (len(p.nodes), node_limit)
    return out
