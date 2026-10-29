# Field log

Problems met while using the server on real jobs, with the cause and an improvement idea.
One entry per problem. "Cause" says whether the server, the script or the model was at fault.

## 2026-10-28: bracket hex mesh (multi-cell STEP, C3D20R, static)

1. **MCP tools missing from the session.** `claude mcp list` showed abaqus connected; ToolSearch found
   no abaqus tools. Cause: the server was registered at user scope at 20:52 (commit 61bd0b8), after the
   session had started (run 20:05-20:37); a client loads MCP servers at session start only.
   Workaround: a CLI calling `Service` directly. Fix: register first, then start the session (or `/mcp`).
2. **No upload for input files.** `run_script` uploads the script only; the STEP, `cells.json` and
   `run.json` went up through the private `_upload`. Cause: server gap.
   Idea: `run_script(..., inputs=[paths])`, or a `put_files(job, paths)` tool.
3. **No download for result files.** Fetching a PNG or JSON written by a script needs `t.get`.
   Cause: server gap. Idea: `get_files(job, names)` into the host project dir.
4. **`mdb.openStep` raised AttributeError.** In `cae noGUI` the `mdb.open*` and part methods exist only
   after `import part` (or `from caeModules import *`). Cause: script. Idea: `run_script` prepends
   `from caeModules import *`, or the tool docstring says so.
5. **Invalid geometry reported late.** The multi-cell import gave `geometryValidity = 0` silently;
   the error came at `seedPart`. Cause: Abaqus import (entry 7); snapping my cut planes to the noisy
   source coordinates did not fix it. Idea: a `check_part` helper that prints validity
   and the `checkGeometry` summary right after import.
6. **Log flood hid the result.** 231 `Error: duplicate vertex` lines in `print_output` pushed the
   script's own summary past the output cap. Cause: server output handling.
   Idea: collapse repeated lines (`<msg> ×231`) and return the tail when truncating.
7. **`combine=True` multi-body import stayed invalid** after the source noise was fixed: 231 duplicate
   vertices, 904 faces for 119 cells. One part per body (`combine=OFF, bodyNum=i`) merged with
   `InstanceFromBooleanMerge(keepIntersections=ON)` gave a valid part, 576 shared faces.
   Cause: Abaqus import behaviour. Idea: note the merge route in the skill or a helper.
8. **`from caeModules import *` shadows Python builtins** (`sum` became the XY-data `sum`: "found
   'generator', expecting a recognized type"). Cause: script; the `_VIEWPORT` template uses the same
   import. Idea: import the modules by name in the templates, and say so in the skill.
9. **Teaching Edition node limit found by a failed run**: "Academic Teaching license is limited to
   250000 nodes" (277k-node job). `job_status` reported it clearly. Idea: `license_check` or the
   README states the limit, and `model_summary` warns when a meshed model exceeds it.
10. **`import displayGroupOdbToolset` failed** ("No module named") when placed before
    `from caeModules import *`; after it, the import works. Cause: script (the module path is set up by
    caeModules). Idea: the skill's post-processing template imports it in that order.
11. **No graded seeds without edge orientation.** `seedEdgeByBias(SINGLE)` needs each edge sorted into
    `end1Edges` / `end2Edges` by its first vertex; a check of node spacings after meshing confirmed the
    direction. Also `p.edges.findAt(((pt,),))` returns a sequence without `getNodes`; `findAt(pt)` returns
    the edge. Cause: script. Idea: a `seed_bias(part, edges, fine_end_point, min, max)` helper.

## 2026-10-29: bracket natively in Abaqus (spec 005 C8)

12. **Native bracket partition left 205 of 636 cells unmeshed** (run 2).
    Tab clamp-hole planes cut through the whole part and left 0.35 mm slivers in the bore wall; a full
    ring r + 1.35 around the bore touched the ligament box planes at a tangent (zero-angle corners).
    A whole-part `generateMesh` gave 0 nodes and no message. Cause: skill (no partition strategy) and
    tool (`cut` selected cells only by points). Fix: `cut(box=...)`, `mesh_report` `unmeshed_at`, skill
    rules on zone-local cuts, tangent points and slivers.
