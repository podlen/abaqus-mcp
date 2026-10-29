"""Kernel-side model views: a plain function of `mdb`, `session` and a viewport, so the same text
runs in a batch kernel (vp = session.viewports['Viewport: 1']) and in a live CAE session. printToFile
names carry no dot (nothing is written otherwise)."""


_VIEW = {"iso": "Iso", "front": "Front", "back": "Back", "top": "Top", "bottom": "Bottom", "left": "Left",
         "right": "Right"}


def render_views(mdb, session, vp, model, base, highlight=None, views=("iso", "front", "top"), size=(900, 600)):
    """Write <base>_<view>.png of the assembly, or of the first part when there are no instances.
    highlight: one set or surface name (assembly, else part), drawn red; a list of names writes
    <base>_<name>_<view>.png per name. Returns {"files": [...], "shown": "assembly"|"part:<name>",
    "highlight": highlight}."""
    import os
    from abaqusConstants import PNG, OFF

    m = mdb.models[model] if model else mdb.models[list(mdb.models.keys())[0]]
    a = m.rootAssembly
    if len(a.instances):
        obj, shown, owner = a, "assembly", a
        a.regenerate()
    else:
        pn = list(m.parts.keys())[0]
        obj, shown, owner = m.parts[pn], "part:" + pn, m.parts[pn]
    many = isinstance(highlight, (list, tuple))
    names = list(highlight) if many else [highlight]
    for h in names:
        if h and h not in owner.sets.keys() and h not in owner.surfaces.keys():
            raise ValueError("no set or surface named %r in %s" % (h, shown))
    vp.setValues(displayedObject=obj)
    session.pngOptions.setValues(imageSize=tuple(size))
    session.printOptions.setValues(vpDecorations=OFF)
    dgname = "mcp_highlight"
    files = []
    try:
        for h in names:
            if h:
                import displayGroupMdbToolset as dgm
                if h in owner.sets.keys():
                    leaf = dgm.LeafFromSets(sets=(h,))
                else:
                    leaf = dgm.LeafFromMeshSurfaceSets(surfaceSets=(h,))
                session.DisplayGroup(name=dgname, leaf=leaf)
                cm = vp.colorMappings["Display group"]
                vp.setColor(colorMapping=cm)
                cm.updateOverrides(overrides={dgname: (True, "#FF0000", "Default", "#FF0000")})
            stem = "%s_%s" % (base, h) if many else base
            for name in views:
                vp.view.setValues(session.views[_VIEW[name]])
                vp.view.fitView()
                out = "%s_%s" % (stem, name)
                session.printToFile(fileName=out, format=PNG, canvasObjects=(vp,))
                if not os.path.exists(out + ".png"):
                    raise RuntimeError("printToFile wrote nothing for " + out)
                files.append(out + ".png")
            if h and dgname in session.displayGroups.keys():
                del session.displayGroups[dgname]
    finally:
        if dgname in session.displayGroups.keys():
            del session.displayGroups[dgname]
    return {"files": files, "shown": shown, "highlight": highlight}
