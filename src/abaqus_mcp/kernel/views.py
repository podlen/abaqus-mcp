"""Kernel-side model views: a plain function of `mdb`, `session` and a viewport, so the same text
runs in a batch kernel (vp = session.viewports['Viewport: 1']) and in a live CAE session. printToFile
names carry no dot (nothing is written otherwise)."""


def render_views(mdb, session, vp, model, base, highlight=None, size=(1200, 800)):
    """Write <base>_iso.png, <base>_front.png, <base>_top.png of the assembly, or of the first
    part when there are no instances. highlight: one set or surface name (assembly, else part).
    Returns {"files": [...], "shown": "assembly"|"part:<name>", "highlight": name|None}."""
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
    vp.setValues(displayedObject=obj)
    dgname = None
    if highlight:
        import displayGroupMdbToolset as dgm
        if highlight in owner.sets:
            leaf = dgm.LeafFromSets(sets=(highlight,))
        elif highlight in owner.surfaces:
            leaf = dgm.LeafFromMeshSurfaceSets(surfaceSets=(highlight,))
        else:
            raise ValueError("no set or surface named %r in %s" % (highlight, shown))
        dgname = "mcp_highlight"
        session.DisplayGroup(name=dgname, leaf=leaf)
        cm = vp.colorMappings["Display group"]
        vp.setColor(colorMapping=cm)
        cm.updateOverrides(overrides={dgname: (True, "#FF0000", "Default", "#FF0000")})
    session.pngOptions.setValues(imageSize=size)
    session.printOptions.setValues(vpDecorations=OFF)
    files = []
    try:
        for name, view in (("iso", "Iso"), ("front", "Front"), ("top", "Top")):
            vp.view.setValues(session.views[view])
            vp.view.fitView()
            out = "%s_%s" % (base, name)
            session.printToFile(fileName=out, format=PNG, canvasObjects=(vp,))
            if not os.path.exists(out + ".png"):
                raise RuntimeError("printToFile wrote nothing for " + out)
            files.append(out + ".png")
    finally:
        if dgname and dgname in session.displayGroups.keys():
            del session.displayGroups[dgname]
    return {"files": files, "shown": shown, "highlight": highlight}
