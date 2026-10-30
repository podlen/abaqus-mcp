# Lean tool output and native partitioning

Status: agreed. Owner: Enej. Branch: 005-lean-tools-native-partition.

Goal: abaqus-mcp is a general Abaqus tool; its first heavy use is a project in another subject with
models far more complex than the test bracket of C8 (coursework geometry, kept outside this repo).
Claude builds partitioned hex meshes inside Abaqus, with fewer tokens per job and fewer failed
rounds. The bracket must be easy (source: Enej, 2026-10-29).

## Criteria
C1. Compact `run_script` output. On success: `print_output` and `stdout`, each with runs of
    consecutive lines identical after `rstrip` collapsed to one line plus ` [xN]`, then cut to the
    last `print_cap` characters (config, default 4000) behind a `[... N chars cut]` head; no `stderr`,
    no `traceback`. Worst case on success: 2 x 4000 characters (was 3 x 20 000). On failure: the same
    collapsed tails plus `stderr` (license lines dropped) and `traceback`.
    check: unit tests with the fake transport: 231 identical lines come back as one line with
    ` [x231]`; a 10 kB output keeps its last 4000 characters; a successful run has no `stderr` key.
C2. Files in and out. `run_script(job, script_path, inputs=[...], outputs=[...])`: `inputs` are host
    files (bare names in the project directory, or paths) uploaded to the job dir before the run;
    `outputs` are file names fetched from the job dir to `<project>/<job>/` after it; the result lists
    `fetched` and `missing`. Names follow the existing filename rules.
    check: unit tests (upload and fetch calls, a missing output, a rejected name); E2E in C9.
C3. Script preamble. `run_script` runs the user's script through a wrapper that first loads
    `caeModules` without a star import (so `mdb.openStep`, part and mesh methods exist and builtins
    such as `sum` are not shadowed) and puts the helper module of C4 on `sys.path`. Traceback line
    numbers and the file name stay those of the user's script. The script runs in a fresh namespace
    (`__name__ == "__main__"`, `__file__` set); nothing else is injected, the script imports what it uses.
    check: E2E: a script that calls `mdb.openStep`, uses `sum(x for x in ...)` and raises on a known
    line returns its printed lines and a traceback naming the script file and that line.
C4. Helper module `abqmcp` (`src/abaqus_mcp/kernel/abqmcp.py`, kernel side, Python 3.10), uploaded
    to the job dir with every `run_script` and to the live dir with every `cae_live`:
    `import_solid` (one part from a STEP; multi-body files by the per-body import plus
    `InstanceFromBooleanMerge` route of field-log entry 7; raises with the validity summary when the
    part is invalid), `cut` (cell partitions at principal-plane offsets x/y/z and at
    point-normal planes; planes that cut nothing are reported, not raised), `mesh_plan` (per cell
    hex STRUCTURED, else hex SWEEP, else tet FREE; returns counts and the non-hex cells with a point on
    each), `seed_bias` (single bias towards a given point on given edges, edge sense sorted by
    vertex distance), `mesh_report` (nodes, elements by type, technique counts, node-limit warning).
    check: E2E on a block with a hole: import, cuts, `mesh_plan` gives 0 tet cells; `seed_bias`
    gives the smallest node spacing at the named end and a last/first spacing ratio within 20 % of
    max/min; `mesh_report` node count equals `model_summary` `mesh.nodes`. E2E on a two-solid STEP
    (`tests/fixtures/two_blocks.step`, made with FreeCAD): `import_solid` returns one valid part
    with 2 cells.
C5. `model_views` takes `highlight` as one name or a list, `views` (default iso, front, top; iso only
    when `highlight` is a list) and `size` (default 900x600). One CAE run for all highlights.
    check: unit test of the call shape; E2E: a list of two highlights returns two PNGs whose IHDR
    width and height read 900 and 600, from one `cae noGUI` run.
C6. `model_summary(only=[...])` returns just the named top-level keys (plus `source`, `model`,
    `omitted`, `status`). The `mesh` section adds per part the cell counts by assigned mesh
    technique, and a warning when meshed nodes exceed config `node_limit` (default 0: off; the
    Teaching Edition limit is 250 000). The count is the mdb one (`mesh.nodes`, parts plus independent
    instances); the solver adds reference-point nodes, so it is a lower bound.
    check: unit test of the filter; E2E on the C4 block: technique counts and the warning with
    `node_limit` below the node count.
C7. Skill. The abaqus-modelling skill gets a partition-and-mesh workflow (single solid import,
    native cuts with `abqmcp`, `mesh_plan` loop, bias seeds, node limit) and token rules (one
    `model_views` call with a list, `model_summary(only=...)`, `outputs` for result files, small
    PNGs). The tool docstrings say what C1-C6 return.
    check: user judges; C8 uses only the skill and the tool docstrings.
C8. Test bracket natively. A fresh sonnet subagent gets the MCP tools, the skill, the bracket STEP,
    feature coordinates, the post-processing scripts and a brief (load case, BCs, shell/core rule,
    section names, mesh sizes). The reference partition and model scripts are withheld (source:
    Enej, 2026-10-29). It builds the reference case (C3D20R, linear static) with all partitions made
    in Abaqus (FreeCAD only for reading feature coordinates or defeaturing), meshes it with 0 tet
    cells, runs it, and the post script gives four stress sites within ±2 % of the reference run.
    A round is one `submit_job` of the full model; at most 3 rounds. A miss after round 3, or any
    blocker, stops the run: Claude reports which part failed (tool, skill or model) and Enej decides
    the fix. The agent reads no server source and calls no private method.
    check: site values against the reference table (coursework notes, outside this repo); grep of the
    agent's transcript (`subagents/*.jsonl`) for reads of `src/abaqus_mcp/` and for `_upload`,
    `t.get`, `Service(`; tool tally from the same file (tokens summed over usage fields, calls by tool
    name) logged next to the 2026-10-28 run, no threshold.
C9. Both transports. Pre-condition: VM up, `bin/abaqus-vpn up`. check: Linux `uv run pytest` passes;
    `ABAQUS_E2E=1 uv run pytest` over ssh passes the cantilever and `tests/test_e2e_partition.py`; inside the VM with the local transport
    `uv run pytest tests/test_windows.py tests/test_tools.py` and the new E2E file pass.

## Facts
- The 2026-10-28 bracket run ran with no MCP tools: the server was registered at user scope at
  20:52 (commit 61bd0b8), after the run (20:05-20:37); MCP servers load at session start.
- That session: 415 turns, 44.5 M cache-read tokens, 77k-130k tokens of context per Abaqus turn.
- Tool schemas: 7.8 kB for all eleven tools (measured with FastMCP `list_tools`).
- `run_script` returned `stdout`, `stderr` and `print_output` each up to `max_output` (20 000 chars).
- `model_views` writes three 1200x800 PNGs per call.
- Reference run: 74 755 nodes, 77 structured and 42 swept cells (2026-10-28).
- Tolerance ±2 % (source: Enej, 2026-10-29); halving the reference mesh size moved the sites 0.6-1.6 %.
- Probe 2026-10-29: in a `cae noGUI` script `sum` is the Abaqus one even without a star import;
  `import caeModules` alone makes `mdb.openStep` exist; `setMeshControls(technique=STRUCTURED)` on an
  unmappable cell raises `AbaqusException: Some regions cannot be Mapped.` and keeps the old control.
- Tool schemas stay under 10 kB after the change: 9531 bytes (measured 2026-10-29, after `imprint`).

## Ruled out
- Partitioning in FreeCAD with a multi-cell STEP export (field-log entries 5, 7, 11).
- A new tool per helper: helpers live in one kernel module that scripts import.
- Image compositing on the host (no Pillow dependency).

## Log
- 2026-10-29: probes in the VM: `openStep(...).numberOfParts` is the body count (no `numberOfBodies`);
  `getMeshControl` takes the cell object, a findAt sequence raises TypeError.
- 2026-10-29: C1-C7, C9 done. Linux `uv run pytest`: 76 passed, 23 skipped. ssh E2E: cantilever,
  upsetting, summary 9 passed; `tests/test_e2e_partition.py` 2 passed. In the VM, local transport:
  `test_windows.py`, `test_tools.py`, `test_e2e_partition.py` 50 passed, 2 skipped. Live plug-in
  reinstalled in the VM (`vm/install-live-plugin.sh`).
- 2026-10-29: C8 inputs in a coursework folder outside this repo.
- 2026-10-29: C8 run 1 (sonnet) blocked before any tool use of the new code: this session's server
  process dated from 2026-10-28 21:12; `/mcp` reconnect restarted it (08:09). The run also found a
  brief error in the core box (fixed in the brief).
- 2026-10-29: C8 run 2 (sonnet) BLOCKED at the mesh, 0 submit_job rounds. 636 cells (568 STRUCTURED,
  68 SWEEP by `mesh_plan`, 0 tet), 512 shell / 124 core cells; whole-part `generateMesh` gave 0
  nodes with no message, per cell 205 unmeshed (seed-count conflicts). Causes the agent named:
  whole-part cuts for one zone's holes made 0.35 mm slivers in another zone (`cut(cells=...)` was not
  used), and a full ring around a hole tangent to box planes. Transcript: no source reads,
  no private calls (grep hits were tool names). Tally: 45 run_script, 61 Bash, 4 Read, 1 set_project;
  14.7 M cache-read, 0.49 M cache-write, 0.27 M output tokens (2026-10-28 run: 44.5 M cache-read).
- 2026-10-29: after run 2: `cut(box=...)`, `mesh_report` `unmeshed_at` (`Cell.getElements()` is None
  when unmeshed), skill partition-strategy rules, field-log entry 12. Partition E2E over ssh: 2 passed.
- 2026-10-29: C8 run 3 (sonnet) BLOCKED after 2 of 3 rounds (plus 2 submit_job calls rejected for
  a missing `cae_file`). Variant A, 102 cells (67 STRUCTURED, 35 SWEEP), 88 283 nodes, 0 unmeshed:
  both rounds failed in the datacheck, "The volume of 122 elements is zero, small, or negative"
  (about 90 where straight walls meet a full ring at a tangent; about 30 at a 0.2 mm sliver).
  Variant B (half ring): 15 bad elements, 2 tet cells; planar cuts on a 25-face shell cell raised
  "Feature creation failed". No sites.
  Transcript: no source reads, no private calls. Tally: 75 run_script, 4 submit_job, 93 Bash,
  4 Read; 23.3 M cache-read, 1.37 M cache-write, 0.46 M output tokens; 4.6 h.
- 2026-10-29: after run 3: `prism`, `tool_box`, `tool_cylinder`, `imprint` in abqmcp. Probe on the
  bracket (profile inset, hole cylinders, two boxes, `min_volume`): valid, 4 cells, core volume equal
  to the FreeCAD reference to 0.01 mm³. ssh E2E `test_imprint` passed (volumes, sets kept through a later cut, no leftover parts).
  Run 3 leftovers moved out of the C8 folder. Round counter for run 4 reset to 3 (source: user).
- 2026-10-29: C8 run 4 (sonnet) MISS after 1 of 3 rounds (job completed, 1 increment). Two sites
  within ±2 % (+1.7 %, −0.1 %), two outside (−3.6 %, −2.7 %); displacement at the load point +0.2 %,
  reaction equal to the load. 86 321 nodes, 242 cells (202 STRUCTURED, 40 SWEEP, 0 tet, 0 unmeshed).
  Route: FreeCAD defeaturing, import_solid, prism + imprint, cut planes; the zone around the loaded
  hole got two 45° diagonal planes through the hole axis, and both missing sites lie in that zone.
  Transcript: no source reads, no private calls. Tally: 24 run_script, 1 submit_job, 30 Bash, 4 Read;
  8.53 M cache-read, 0.36 M cache-write, 0.18 M output tokens; 18 min.
