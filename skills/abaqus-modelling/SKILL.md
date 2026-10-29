---
name: abaqus-modelling
description: Method advice for Abaqus/Standard models read through the abaqus-mcp tools (model_summary, model_views, cae_live). Covers inferring the modelling objective from a model, symmetry and axisymmetric reduction, boundary conditions and loads, element choice (CAX4R, CAX4, C3D8R, C3D8I, C3D10M, CPE/CPS, shells), hourglassing and locking, rigid tools and reference points, contact pairs (main/secondary, surface-to-surface, friction, overclosure), mesh refinement, NLGEOM, Static General incrementation, and convergence trouble (cut-backs, negative eigenvalues, excessive distortion, ALLAE/ALLIE energy checks, hand-calc validation). Use when the user sets up, reviews or debugs an Abaqus model, asks which element, BC, load or contact setting to use, or a job does not converge.
---

# Abaqus modelling advice

The user is a mechanical engineer strong in FEM and structural dynamics: skip textbook basics.
Typical work: Abaqus/Standard, nonlinear plasticity, contact, small increments.

Abaqus 2026 names the two contact surfaces `main` and `secondary`. Use only these words.

## Sources

Every rule ends with its source tag:

- `[A: <title>]`: a page of the Abaqus 2026 documentation, by page title. A local copy's path,
  if any, is in `.team/local.md`.
- `[Bathe x.y]`: K.-J. Bathe, *Finite Element Procedures*, Prentice Hall 1996, section x.y.
- `[Reddy x.y]`: J. N. Reddy, *An Introduction to the Finite Element Method*, 4th ed., McGraw Hill 2018, section x.y.
- `[TBD]`: no verified source. Tell the user the rule is unsourced when you give it.

Quote the tag with the advice, so the user can look it up.
Cite only the tag of the rule you apply. A number or claim that no rule here states (an element count, a handbook fit, a coefficient) gets `[TBD]`, even when you are confident of it.

## Workflow

0. Ask the user for the analysis directory of this project (an existing one with the model files, or a new
   location under their home directory). Call `set_project(path)`. Switch projects with a second call.
   Job tools return "no project: call set_project" until then. Input files at `<path>/` are found by name.
1. Read the model with `model_summary(job)`.
   With a live CAE session and no `cae_file` it reads the open model, unsaved edits included.
   For a saved file pass `cae_file`.
   Check `omitted` before calling anything absent: long lists are cut.
2. Look at the model with `model_views(job, highlight=[<name>, ...])`.
   Put every contact surface and every BC set whose position matters in one list: one CAE run, one iso PNG per name.
   Read the PNGs yourself.
3. Infer the objective (table below). State it to the user in one or two sentences.
4. Ask what the model cannot show (list below). Ask in one message.
5. Compute the expected result by hand with the model's own dimensions and material, and write the numbers down.
   Name the closed-form case it reduces to, from a handbook or an elasticity or plasticity text.
   For several responses (modes, load paths), estimate each family and sort them by value; do not guess an order.
   Where no closed form applies, say so and give the bound or estimate you can compute.
   Use these numbers in step 6: mesh size at a stress peak (M13), number of modes or increments, the check after the run.
6. Advise. Run the red-flag checks below, then the topic rules in `references/`.
   Each piece of advice carries its source tag.
7. Edit the model through `cae_live` only after the user agrees to that specific edit.
   The edit lands in the user's open model tree.
8. After a run:
   - `job_status(job)`: increments, cut-backs, grouped warnings.
   - `odb_history(job, outputs=[...])`: RF and U at the tool reference point; ALLIE, ALLAE, ALLSD, ALLPD.
   - `odb_query(job, ...)`: COPEN, CPRESS, PEEQ and S fields.
   - Then the checks in `references/solution-and-checks.md`.

## Building a partitioned hex mesh

Make all partitions in Abaqus. A multi-cell STEP from a CAD tool gave an invalid part with duplicate vertices (docs/field-log.md, entries 5 and 7).
Scripts run through `run_script(job, script, inputs=[...], outputs=[...])`.
Each script imports what it uses (`from abaqus import mdb`, `from abaqusConstants import *`).
The helpers come from `import abqmcp as h`:

1. `p = h.import_solid("part.step", "Name")` gives one valid part. A file with several bodies is merged into one part with shared faces. An invalid result raises with the entity counts.
2. `h.cut(p, x=[...], y=[...], z=[...], planes=[((pt), (normal)), ...], cells=[pt, ...])` cuts cells by planes.
   Cut through every hole axis and every step in the outline, so each cell becomes a brick or a sweepable prism.
   Planes that cut nothing are listed in `skipped`.
3. `h.mesh_plan(p)` tries hex STRUCTURED, then hex SWEEP, per cell, and falls back to tet FREE.
   It returns the technique counts and a point on each non-hex cell.
   Add cuts through the cells in `non_hex` and run it again; `tet=False` leaves those cells unassigned.
4. Seeds: `p.seedPart(size=h0)`, then `h.seed_bias(p, edges=[pt, ...], fine=pt, min_size, max_size)` for grading toward a stress peak.
   `seed_bias` works out the sense of each edge itself.
5. `p.generateMesh()`, then `h.mesh_report(p)`: nodes, element types, techniques, unmeshed cells, quality checks.
   It warns above 250 000 nodes, the Teaching Edition limit.
6. Save the .cae in the same script. Check the mesh with `model_summary(job, cae_file=..., only=["mesh"])`, whose `mesh.techniques` counts cells per technique.

One script builds the whole model: geometry, cuts, mesh, sections, steps, loads and BCs.
After a failed run, fix that script and rerun it. A new script for each step costs a CAE start each time.

## Token use

Every tool result stays in the context for the rest of the session.

- `print()` only what you decide on: counts, a validity flag, a short dict.
  `run_script` returns the last 4000 characters of `print_output` and `stdout`, with repeated lines collapsed.
- Write bulky results (node tables, per-cell lists) to a file, fetch it with `outputs=[...]`, and read only the part you need.
- `model_summary(..., only=["mesh"])` (or `["steps", "loads", "bcs"]`) after the first full read.
- `model_views` takes a list of highlights and `views=["iso"]`. A PNG costs about width x height / 750 tokens: 900 x 600 is about 720.
  Ask for a view only when a picture decides something.
- Do not read the server source or call private methods; the tool docstrings say what each tool returns.

## Inferring the objective from the summary

| summary field | reading |
|---|---|
| `parts.*.dim` = `AXI` | Axisymmetric reduction chosen. Geometry, material, loads and BCs must be independent of θ. |
| `parts.*.type` = `ANALYTIC_RIGID_SURFACE`, or a part used in a rigid body | Rigid tooling driven through a reference point. |
| `materials.*.plastic` present | Elastic-plastic analysis. The table range of plastic strain bounds the trustworthy strain range. |
| `bcs` with nonzero `values` on a reference-point set | Displacement-controlled loading. The quantity of interest is likely the RP reaction force against stroke. |
| `loads` with a force on a reference point | Load control. A limit load ends the run in cut-backs (see `references/solution-and-checks.md`). |
| `interactions` with `main`/`secondary`, `contact_props.*.friction` | Contact problem; friction sensitivity may be part of the question. |
| set or surface names (`sym`, `axis`, `fix`, `top`) | Intended BC locations. Confirm with `model_views`. |
| `bbox` with one dimension much smaller than the others | Thin body: shell or plane-stress candidate. |
| `mesh.unmeshed` not empty, or `steps` empty | Model under construction: advise on the missing part first. |
| `steps[].nlgeom`, `initial_inc`, `max_inc` | How far the user has thought about nonlinearity and incrementation. |

A field that is absent carries no evidence. Ask.

## Ask the user

Ask only for items the summary and views cannot answer:

- The quantity of interest: force-stroke curve, final shape, PEEQ at a location, contact pressure, residual stress.
- The unit system. The summary carries numbers only.
- The friction coefficient and its origin, when `contact_props` has none.
- Whether the real loads, supports and material are symmetric about the planes the model uses.
- Whether the tool is stiff enough to be rigid in the real setup.
- The accuracy target for mesh and increment studies.
- A reference value for validation: a test result, a handbook value, or the hand calc the user trusts.

A claim about the physical setup needs the user's word. Otherwise write `[TBD]` and draw no conclusion from it.

## Red-flag checks on a summary

Each check reads one or two summary fields.

1. `steps[].nlgeom` false or absent while plastic strains, rotations or contact sliding are large: switch NLGEOM on.
   Abaqus/Standard defaults to small displacement. Once on, NLGEOM stays on in all following steps.
   `[A: General and Perturbation Procedures]` `[A: Static Stress Analysis]`
2. `steps[].initial_inc` absent: Abaqus tries the whole step load in one increment. Give a reasonable initial increment.
   `[A: Solving Nonlinear Problems]`
3. `steps[].inc_method` = `FIXED` with plasticity or contact: an element-calculation problem terminates the run. Automatic incrementation cuts back instead.
   `[A: Convergence Criteria for Nonlinear Problems]`
4. `steps[].min_inc` close to `initial_inc`: the run stops once a cut-back goes below `min_inc`.
   `[A: Solving Nonlinear Problems]`
5. `mesh.types` holds first-order triangles or tetrahedra (CPE3, CPS3, CAX3, C3D4) in a stress analysis: replace them.
   `[A: Solid (Continuum) Elements]`
6. `mesh.types` holds C3D20, CAX8 or CPE8 with a Mises `plastic` material: volumetric locking.
   `[A: Solid (Continuum) Elements]` `[Bathe 4.4.3]`
7. `mesh.types` holds hybrid elements (`...H`) with an elastic-plastic metal: no advantage, extra cost.
   `[A: Solid (Continuum) Elements]`
8. An interaction whose `secondary` is an analytical rigid surface: it must be `main`.
   `[A: Analytical Rigid Surface Definition]` `[A: Contact Formulations in Abaqus/Standard]`
9. An analytical rigid part: check its normal (gotcha below).
10. A rigid body reference point with fewer constrained DOFs than active DOFs: unconstrained rigid-body motion.
    `[A: Common Difficulties Associated with Contact Modeling in Abaqus/Standard]` `[A: Rigid Body Definition]`
11. A deformable body held only by contact or friction in step 1: it has no stiffness against rigid-body motion before contact pressure builds.
    `[A: Common Difficulties Associated with Contact Modeling in Abaqus/Standard]`
12. An `AXI` part with `bbox` xmin < 0: the radial coordinate of every node must be positive.
    `[A: Boundary Conditions]`
13. An `AXI` model with no BC on the nodes at r = 0: Abaqus adds none. A radial BC there is recommended for nonlinear problems.
    `[A: Axisymmetric Solid Element Library]`
14. `materials.*.plastic.table`: first row plastic strain must be 0; values are true stress and logarithmic plastic strain.
    `[A: Inelastic Behavior]`
15. Beyond the last plastic strain in the table the yield stress stays constant by default. Compare the last row with the expected PEEQ.
    `[A: Classical Metal Plasticity]`
16. `contact_props` without `friction`: the contact is frictionless by default. Ask whether that is intended.
    `[A: Frictional Behavior]`

## Gotcha: analytical rigid segment direction

An analytical rigid surface is single-sided.
Its outward normal follows the order of the line segments: n = e3 × s, with s running from the start of the first segment to the end of the last.
Segments in the wrong order flip the normal; only reversing the segment sequence fixes it.
`[A: Analytical Rigid Surface Definition]`

With surface-to-surface discretization, Abaqus ignores contact when the single-sided secondary and main normals point in roughly the same direction (positive dot product).
`[A: About Contact Pairs in Abaqus/Standard]`

Result: the tool passes through the body with zero contact force, and the run converges.
A second outcome is documented: severe overclosure at every secondary node, then non-convergence.
`[A: Modeling issues for rigid surfaces in Abaqus/Standard]`
Check before a run: `model_views(job, highlight=<rigid surface>)` and the segment order in the sketch.
The normal is the segment vector rotated 90° counterclockwise; it must point toward the deformable body.
`[A: Modeling issues for rigid surfaces in Abaqus/Standard]`
Check after a run: the RP reaction force stays at zero while the tool moves (`odb_history`).

## Topic rules

Load the file for the topic at hand:

- `references/reduction-and-bcs.md`: symmetry, axisymmetry, boundary conditions, loads.
- `references/elements-and-mesh.md`: element families, hourglassing, locking, shells, mesh refinement.
- `references/contact-and-rigid.md`: rigid bodies, analytical rigid surfaces, contact pairs, friction, overclosure.
- `references/solution-and-checks.md`: NLGEOM, incrementation, convergence diagnosis, energy checks, validation.
