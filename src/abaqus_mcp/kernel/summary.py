"""Kernel-side model summary: plain functions of an `mdb`, with no call that exists only in a batch
kernel, so the same text runs in a live CAE session. abaqus_scripts.model_summary embeds this file
into the kernel script; keep it free of module-level Abaqus imports and of relative imports. Python
3.10 (Abaqus 2026 kernel). Output format: docs/model_summary.schema.json."""
import json

LIMITS = dict(parts=20, instances=30, sets=30, surfaces=30, features=15, materials=20, rows=20,
              sections=20, assignments=30, steps=20, loads=30, bcs=30, interactions=20,
              contact_props=10, types=15, radii=10)


def _cut(seq, key, path, scale, omitted):
    n = max(1, int(LIMITS[key] * scale))
    items = list(seq)
    if len(items) > n:
        omitted[path] = len(items) - n
    return items[:n]


def _num(v):
    try:
        return float(v)
    except Exception:
        return None


def _table(tab, path, scale, omitted):
    rows = []
    for r in _cut(tab or (), "rows", path, scale, omitted):
        vals = [_num(x) for x in r]
        rows.append([x for x in vals if x is not None])
    return rows


def _counts(obj):
    c = {}
    for k, a in (("cells", "cells"), ("faces", "faces"), ("edges", "edges"), ("vertices", "vertices"),
                 ("nodes", "nodes"), ("elems", "elements")):
        try:
            v = getattr(obj, a)
            n = len(v) if v is not None else 0
        except Exception:
            continue
        if n:
            c[k] = n
    return c


def _named(repo, key, path, scale, omitted):
    return {n: _counts(o) for n, o in _cut(repo.items(), key, path, scale, omitted)}


def _region(r):
    """Set or surface name of a Region. Abaqus gives a tuple (name, owner, ...); else its text."""
    if r is None:
        return None
    if isinstance(r, (tuple, list)) and r and isinstance(r[0], str):
        return r[0]
    return str(r)


def _created(m, repo_attr, state_attr, name):
    """Step name and state object of the step that creates a load, BC or interaction: its state
    there has status CREATED (the object itself holds no step data)."""
    for sn, st in m.steps.items():
        try:
            state = getattr(st, state_attr)[name]
            if str(state.status) == "CREATED":
                return sn, state
        except Exception:
            pass
    return "", None


def _bbox(p):
    try:
        bb = p.queryGeometry(printResults=False)["boundingBox"]
        if bb:
            return [float(x) for pt in bb for x in pt]
    except Exception:
        pass
    try:
        pts = [v.pointOn[0] for v in p.vertices]
        if pts:
            return [min(c[i] for c in pts) for i in range(3)] + [max(c[i] for c in pts) for i in range(3)]
    except Exception:
        pass
    return None


def _radii(ents):
    """Distinct radii (4 significant digits, ascending) of the entities that have one (circular edges,
    cylindrical or spherical faces). getRadius raises for the others."""
    r = set()
    for e in ents:
        try:
            v = float(e.getRadius())
        except Exception:
            continue
        if v > 0:
            r.add(float("%.4g" % v))
    return sorted(r)


def _place(d, i, p):
    """Assembly-frame bbox, translation and rotation of an instance."""
    tr, rot = None, None
    try:
        tr = [float(x) for x in i.getTranslation()]
        r = i.getRotation()
        rot = [float(x) for x in tuple(r[0]) + tuple(r[1])] + [float(r[2])]
    except Exception:
        pass
    if tr and any(abs(x) > 1e-12 for x in tr):
        d["translation"] = tr
    turned = bool(rot) and abs(rot[6]) > 1e-12
    if turned:
        d["rotation"] = rot
    bb = _bbox(p) if (p is not None and tr is not None and not turned) else None
    if bb:
        bb = [bb[k] + tr[k % 3] for k in range(6)]
    else:
        bb = _bbox(i)
    if bb:
        d["bbox"] = bb


_DIM = {"THREE_D": "3D", "TWO_D_PLANAR": "2D", "AXISYMMETRIC": "AXI"}


def _types(elems):
    t = {}
    for e in elems:
        k = str(e.type)
        t[k] = t.get(k, 0) + 1
    return t


def _values(state, names):
    v = {}
    if state is None:
        return v
    for a in names:
        try:
            if str(getattr(state, a + "State")) == "UNSET":
                continue
        except Exception:
            pass
        x = getattr(state, a, None)
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            v[a] = float(x)
    return v


LOAD_FIELDS = ("cf1", "cf2", "cf3", "cm1", "cm2", "cm3", "magnitude", "pressure", "comp1", "comp2", "comp3")
BC_FIELDS = ("u1", "u2", "u3", "ur1", "ur2", "ur3")


def _build(mdb, model, source, scale):
    om = {}
    mname = model or list(mdb.models.keys())[0]
    m = mdb.models[mname]
    a = m.rootAssembly
    out = {"source": source, "model": mname, "models": list(mdb.models.keys()), "omitted": om}

    parts, nodes_of, types_of = {}, {}, {}
    unmeshed = []
    for pn, p in _cut(m.parts.items(), "parts", "parts", scale, om):
        d = {"dim": _DIM.get(str(p.space), str(p.space)), "type": str(p.type),
             "cells": len(p.cells), "faces": len(p.faces), "edges": len(p.edges)}
        if len(p.vertices):
            d["vertices"] = len(p.vertices)
        bb = _bbox(p)
        if bb:
            d["bbox"] = bb
        d["features"] = _cut(p.features.keys(), "features", "parts.%s.features" % pn, scale, om)
        for k, ents in (("edge_radii", p.edges), ("face_radii", p.faces)):
            rr = _radii(ents)
            if rr:
                d[k] = _cut(rr, "radii", "parts.%s.%s" % (pn, k), scale, om)
        d["sets"] = _named(p.sets, "sets", "parts.%s.sets" % pn, scale, om)
        d["surfaces"] = _named(p.surfaces, "surfaces", "parts.%s.surfaces" % pn, scale, om)
        parts[pn] = d
        nodes_of[pn] = len(p.nodes)
        types_of[pn] = _types(p.elements)
        rigid = "ANALYTIC" in str(p.type)
        if not rigid and (d["cells"] or d["faces"] or d["edges"]) and not len(p.elements):
            unmeshed.append(pn)
    out["parts"] = parts

    inst, tot_nodes, tot_el, types = {}, 0, 0, {}
    for iname, i in a.instances.items():
        dep = bool(getattr(i, "dependent", True))
        if len(inst) < max(1, int(LIMITS["instances"] * scale)):
            inst[iname] = {"part": i.partName, "dependent": dep}
            _place(inst[iname], i, m.parts[i.partName] if i.partName in m.parts.keys() else None)
        else:
            om["instances"] = om.get("instances", 0) + 1
        if dep:
            pn = i.partName
            if pn in nodes_of:
                tot_nodes += nodes_of[pn]
                for k, v in types_of[pn].items():
                    types[k] = types.get(k, 0) + v
        else:
            tot_nodes += len(i.nodes)
            for k, v in _types(i.elements).items():
                types[k] = types.get(k, 0) + v
            if len(i.elements) and i.partName in unmeshed:
                unmeshed.remove(i.partName)  # meshed on the independent instance
    if not len(a.instances):
        for pn in nodes_of:
            tot_nodes += nodes_of[pn]
            for k, v in types_of[pn].items():
                types[k] = types.get(k, 0) + v
    tot_el = 0
    for v in types.values():
        tot_el += v
    out["instances"] = inst
    out["sets"] = _named(a.sets, "sets", "sets", scale, om)
    out["surfaces"] = _named(a.surfaces, "surfaces", "surfaces", scale, om)

    mats = {}
    for mn, mat in _cut(m.materials.items(), "materials", "materials", scale, om):
        d = {}
        el = getattr(mat, "elastic", None)
        if el is not None:
            d["elastic"] = {"type": str(getattr(el, "type", "")),
                            "table": _table(el.table, "materials.%s.elastic" % mn, scale, om)}
        pl = getattr(mat, "plastic", None)
        if pl is not None:
            d["plastic"] = {"hardening": str(getattr(pl, "hardening", "")),
                            "table": _table(pl.table, "materials.%s.plastic" % mn, scale, om)}
        de = getattr(mat, "density", None)
        if de is not None:
            d["density"] = _table(de.table, "materials.%s.density" % mn, scale, om)
        mats[mn] = d
    out["materials"] = mats

    secs = {}
    for sn, s in _cut(m.sections.items(), "sections", "sections", scale, om):
        d = {"type": s.__class__.__name__}
        mt = getattr(s, "material", None)
        if isinstance(mt, str) and mt:
            d["material"] = mt
        th = _num(getattr(s, "thickness", None))
        if th is not None:
            d["thickness"] = th
        secs[sn] = d
    out["sections"] = secs
    asg = []
    for pn, p in m.parts.items():
        for sa in p.sectionAssignments:
            e = {"part": pn, "section": sa.sectionName}
            r = _region(getattr(sa, "region", None))
            if r:
                e["region"] = r
            asg.append(e)
    out["assignments"] = _cut(asg, "assignments", "assignments", scale, om)

    steps = []
    for sn, s in _cut(m.steps.items(), "steps", "steps", scale, om):
        d = {"name": sn, "procedure": s.__class__.__name__}
        ng = getattr(s, "nlgeom", None)
        if ng is not None:
            d["nlgeom"] = str(ng) == "ON"
        for k, a_ in (("time_period", "timePeriod"), ("initial_inc", "initialInc"),
                      ("min_inc", "minInc"), ("max_inc", "maxInc")):
            v = _num(getattr(s, a_, None))
            if v is not None:
                d[k] = v
        mn_ = getattr(s, "maxNumInc", None)
        if isinstance(mn_, int):
            d["max_num_inc"] = mn_
        im = getattr(s, "timeIncrementationMethod", None)
        if im is not None:
            d["inc_method"] = str(im)
        steps.append(d)
    out["steps"] = steps

    def bag(repo, key, state_attr, fields):
        res = []
        for n, o in _cut(repo.items(), key, key, scale, om):
            sn, state = _created(m, key, state_attr, n)
            e = {"name": n, "type": o.__class__.__name__, "step": sn}
            r = _region(getattr(o, "region", None))
            if r:
                e["region"] = r
            v = _values(state, fields)
            if v:
                e["values"] = v
            res.append(e)
        return res
    out["loads"] = bag(m.loads, "loads", "loadStates", LOAD_FIELDS)
    out["bcs"] = bag(m.boundaryConditions, "bcs", "boundaryConditionStates", BC_FIELDS)

    ints = []
    for n, o in _cut(m.interactions.items(), "interactions", "interactions", scale, om):
        sn, state = _created(m, "interactions", "interactionStates", n)
        e = {"name": n, "type": o.__class__.__name__, "step": sn}
        ip = getattr(state, "interactionProperty", None) if state is not None else None
        if ip:
            e["prop"] = str(ip)
        for k, attr in (("discretization", "enforcement"), ("sliding", "sliding")):
            v = getattr(o, attr, None)
            if v is not None and str(v):
                e[k] = str(v)
        for k in ("main", "secondary"):
            r = _region(getattr(o, k, None))
            if r:
                e[k] = r
        ints.append(e)
    out["interactions"] = ints

    cps = {}
    for n, cp in _cut(m.interactionProperties.items(), "contact_props", "contact_props", scale, om):
        d = {}
        tb = getattr(cp, "tangentialBehavior", None)
        if tb is not None:
            try:
                d["friction"] = [float(x) for x in tb.table[0]]
            except Exception:
                pass
        nb = getattr(cp, "normalBehavior", None)
        if nb is not None:
            d["normal"] = str(getattr(nb, "pressureOverclosure", ""))
        cps[n] = d
    out["contact_props"] = cps

    out["mesh"] = {"nodes": tot_nodes, "elems": tot_el,
                   "types": dict(_cut(types.items(), "types", "mesh.types", scale, om)),
                   "unmeshed": unmeshed}
    return out


def model_summary(mdb, model=None, source="live", max_bytes=20000):
    """Dict per docs/model_summary.schema.json; cut harder until its JSON is <= max_bytes."""
    for scale in (1.0, 0.5, 0.25, 0.1, 0.03):
        d = _build(mdb, model, source, scale)
        if len(json.dumps(d)) <= max_bytes:
            break
    return d
