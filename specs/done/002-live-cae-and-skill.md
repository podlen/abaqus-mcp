# Abaqus copilot: live CAE session, model advice, nonlinear runs

Goal: Claude works next to Enej in a live Abaqus CAE session. It reads the model Enej has
open, advises on how to model it, edits it so the change appears in Enej's session, and
runs and diagnoses nonlinear Abaqus/Standard jobs (source: Enej, 2026-10-28).
Status: closed (source: Enej, 2026-10-28). C1, C2, C3 live half and the C9 screenshot not run; see backlog.
Builds on specs/done/001-vm-and-mcp-server.md (pushed as 87d46ca).

## Criteria
C1. GUI from Omarchy. `./setup.sh gui` (idempotent stage, no sudo) enables RDP in the VM.
    `bin/abaqus-gui` starts the VM if it is off, runs `abaqus-vpn up`, and opens an
    xfreerdp3 window on the VM. The password goes in by stdin or a file, never on the
    command line. The RDP login is the ssh account `abaqus`, so the GUI session and the
    MCP share one workspace. CAE starts in that session, always with `-mesa` (qxl, no
    3D). Enej uses it to build complex models by hand.
    check: user judges: CAE opens a model, the viewport rotates and redraws. `ps aux`
    while the window is open shows no password.
C2. Live bridge. A CAE GUI plugin in the VM loads at CAE start-up. Every 0.5 s a GUI
    timer checks an inbox folder in the VM workspace and passes each new script to the
    open session's kernel with `sendCommand`. A wrapper around the script writes its
    output or traceback to an outbox file, because `sendCommand` returns no output.
    The plugin writes a heartbeat file with a timestamp every 1 s. MCP tool
    `cae_live(script)` uploads the script over scp, polls the outbox every 0.25 s and
    returns the result. Every live script is kept in a log folder in the VM workspace.
    A script waits until no GUI procedure is active, so an open dialog or pick is never
    disturbed (source: user, 2026-10-28). The Claude Code permission prompt on each
    `cae_live` call is the approval gate.
    check, with the VM running, the VPN up, CAE open through C1 and a small model loaded:
    (a) a script that adds a material makes it appear in Enej's model tree (user
        judges); the median round trip of 5 such calls is <= 2 s;
    (b) a script with a deliberate error returns its traceback, and the next call works;
    (c) with no CAE open, or a heartbeat older than 3 s, `cae_live` returns "no live CAE
        session" within 5 s;
    (d) timer design: `Get-NetTCPConnection -State Listen` in the VM lists the same ports
        before and after the plugin loads. Socket fallback: the new listener is bound to
        127.0.0.1 only and rejects a call without the token.
C3. Model summary and views. MCP tool `model_summary` returns JSON for a saved .cae
    (noGUI) or for the live session (through C2): parts (2D, 3D or axisymmetric,
    bounding box, cell/face/edge counts, features), instances, sets and surfaces with
    entity counts, materials (elastic and plastic data), sections and assignments, steps
    (procedure, NLGEOM, increment settings), loads, BCs, interactions and contact
    properties, mesh (element types, counts, unmeshed parts). The field names are fixed
    in `docs/model_summary.schema.json`, written before the code. The JSON states its
    source (`live` or the .cae path). When a live session exists, `model_summary` and
    `model_views` read it through C2 (unsaved edits included, no second CAE token);
    the noGUI path reads saved files only. Output stays under 20 kB; longer lists are
    cut with a count of the omitted items. MCP tool `model_views` returns iso, front and
    top PNGs of the model, optionally with one named set or surface highlighted.
    check: pytest (gated by ABAQUS_E2E=1) builds a test .cae by script with known
    contents and compares every schema field to them, saved and live. Views: user
    judges one set of images.
C4. Modelling skill. `skills/abaqus-modelling/SKILL.md` in the repo, linked into
    ~/.claude/skills by a README step. It holds method rules: symmetry and axisymmetric
    reduction, element choice for plasticity, contact and bending (CAX4R, C3D8R, C3D8I,
    hourglass control), contact master/slave choice, rigid surfaces with reference
    points, mesh refinement at contact and notches, Standard increment control, and how
    to read the C3 summary to infer the modelling objective. Every rule names its source
    (see Facts for the source set). The skill contains none of the test models below
    and none of their rubric items as worked examples.
    check: two test .cae files without BCs, loads or steps:
    (1) a 3D cylinder billet D = H = 20 mm between two 3D plates, elastic material
        only; prompt "I want to simulate upsetting of this billet. Help me set it up."
        Advice must name: axisymmetric reduction plus half-height symmetry; CAX4R;
        plates as analytical rigid surfaces with BCs on reference points;
        surface-to-surface contact with plates as master and friction as a stated
        choice; plastic material data needed; NLGEOM on; Static, General with a small
        initial increment and automatic incrementation.
    (2) a 3D plate 200 x 100 x 2 mm with a central hole D = 20 mm; prompt "I want the
        stress concentration at the hole under tension along the long side."
        Advice must name: quarter symmetry with symmetry BCs; plane stress (CPS4/CPS8 or
        CPS8R) or shells; mesh refinement at the hole; linear static; an expected Kt
        with its nominal-stress basis, within 2.4-2.6 on net section or 3.0-3.3 on gross
        section (Heywood: Kt,net = 2 + (1 - d/W)^3 = 2.51, Kt,gross = 3.14 at d/W = 0.2).
    (3) held out: fixed at the three models the critic picked, each rubric written before
        the skill or advice was read: thick cylinder (.critic/heldout.md), cantilever strip
        modal (.critic/heldout-2.md), roller on block, Hertz (.critic/heldout-3.md). Each
        passes with at most one rubric item missed and no wrong claim; scored on the advice
        from the latest skill. A gap found after these is an item for the next goal, not a
        new held-out round. (source: user, 2026-10-28)
        Cylinder rerun once after review-5 (one false number); a second fail closes C4 (3) as
        2 of 3 and moves the gap to the next goal. (source: user, 2026-10-28)
    A fresh subagent with only the skill, the MCP tools and the .cae writes the advice;
    the critic scores the rubric (every item required for (1) and (2)). Usefulness: user judges.
C5. Convergence detail. `job_status` adds, per step: increments done, attempts,
    cut-backs, max and mean equilibrium iterations, severe discontinuity iterations,
    smallest and last time increment, step time reached. Definitions on the .sta table
    (columns STEP INC ATT SEVERE-DISCON-ITERS EQUIL-ITERS TOTAL-ITERS TOTAL-TIME
    STEP-TIME INC-OF-TIME): one row is one attempt; a cut-back is a row whose ATT field
    ends in `U`; increments done are rows without `U`. From .msg: warnings grouped by
    type with counts and the first increment where each appears (negative eigenvalues,
    contact overclosure and chatter, excessive distortion, plasticity strain-increment
    warnings); any other warning is grouped by its first line with all numbers removed.
    Also the last error lines. Output stays under 100 lines.
    check: pytest on real .sta/.msg files from the C7 run and from a run of the C7 model
    with the initial increment set to the full step time (forces cut-backs); every
    count equals a count from an awk/grep written from these definitions, not from the
    parser.
C6. History output. MCP tool `odb_history(job, step?, region?, outputs?)` lists the
    history regions and outputs when called without outputs, and returns time series
    otherwise (for example ALLKE, ALLIE, ALLAE, ALLWK, ALLMW where present, RF2 at a
    reference point), cut to at most 200 points with first, last, min and max kept.
    Runs under `abaqus python` (no CAE token).
    check: on the C7 run, RF2 at the plate reference point matches the `*NODE PRINT`
    table in the .dat file (written by the solver, independent of the odb API) to the
    printed precision at every increment the .dat lists; the listing names ALLIE, ALLKE
    and ALLAE.
C7. Upsetting benchmark, built and run through the MCP tools. Units mm, N, MPa.
    Axisymmetric cylinder R0 = 10, H0 = 20, half height (10) by symmetry, 10 x 10 CAX4R
    elements; elastic-perfectly plastic steel (E = 210000, nu = 0.3, sigma_y = 250);
    frictionless analytical rigid plate with a reference point; NLGEOM on; Static,
    General with small increments; plate moves 5 from the start (h = 0.5 H0). History
    output: RF2 and U2 at the plate reference point, every increment, plus the ALL*
    energies; `*NODE PRINT` of RF2 at the same point to the .dat.
    check: plate force within 1 % of sigma_y * pi * R0^2 * H0 / h at plate displacement
    1, 3 and 5 (h/H0 = 0.9, 0.7, 0.5; see Prediction); ALLAE/ALLIE at the end reported
    by C6.
C8. Tests. `uv run pytest` passes without Abaqus (stubs for every new tool); the E2E
    tests pass with ABAQUS_E2E=1 on the VM.
C9. GitHub page. README covers install and use of the new tools and the skill, facts
    only, with a better layout, a CAE screenshot from C1 and badges (license, Python,
    tests).
    check: user judges the page on GitHub, and that the screenshot shows no IP, host
    name, user name or password.
C10. Repo stays publishable. Commits have no Co-Authored-By trailer. main is pushed to
    podlen/abaqus-mcp after the final critic pass, on Enej's go.
    check: `git grep -nE "$(cat .team/publish-patterns)"
    $(git rev-list --all)` returns nothing; `git ls-files` lists no .ovpn, .pem,
    config.local.toml or .admin-password.

## Facts
- Scope is the tool for Abaqus work in general, not the seminar model (source: Enej,
  2026-10-28).
- Preferred mode: Enej builds complex models in the CAE GUI and Claude helps through the
  MCP; Claude builds simple models alone (source: Enej, 2026-10-28).
- Typical use: nonlinear plasticity in Abaqus/Standard with very small increments (source:
  Enej, 2026-10-28).
- VM `abaqus-win` on qemu:///system: Windows 11 Enterprise eval 24H2, admin `abaqus`,
  password in git-ignored .admin-password, `ssh abaqus-vm`, remote shell PowerShell 5.1.
  Display: VNC on 127.0.0.1 with qxl video, no 3D. The VM does not autostart.
- Abaqus 2026 Teaching Edition is installed in the VM; `abaqus_cmd` is
  `C:\Program Files\SIMULIA\Commands\abaqus.bat`; kernel scripts are Python 3.10.
- `abaqus cae noGUI` exits 0 on an uncaught exception, sends `print()` to abaqus.rpy and
  writes the traceback to stderr without its header (CLAUDE.md).
- License: DSLS over the split-tunnel OpenVPN `fs-abaqus`, driven by `bin/abaqus-vpn`.
  Never run `nmcli -s` or `--show-secrets`, never modify the connection.
- Live bridge design: GUI-side timer (no listening port). Unverified whether the Abaqus GUI
  toolkit exposes a timer to a plugin; a short test in the VM settles it. Fallback if
  not: a socket server inside CAE bound to 127.0.0.1 in the VM, token-protected,
  reached through an ssh tunnel (source: Enej agreed, 2026-10-28).
- Existing design rules in docs/decisions.md hold (ssh/scp link, name validation, JSON
  results fetched by scp, exit codes not trusted).
- Git: no Co-Authored-By trailer in commits.
- Prior art and ratings: docs/prior-art.md.
- The repo root is a git repository (`.git` present; HEAD 87d46ca, checked 2026-10-28).
  `.critic/spec.md` is a symlink to this file.
- Skill sources: Abaqus 2026 documentation (by page title) and two textbooks: Bathe, Finite
  Element Procedures (1996), and Reddy, An Introduction to the Finite Element Method, 4th ed.
  (2018); cite by section (source: Enej, 2026-10-28).
- License: Teaching Edition checkout over DSLS works, QAE with 20 seats (checked
  2026-10-28 in the first goal).
- `bin/abaqus-vpn` runs on the host without sudo; the VM reaches the license server
  through libvirt NAT and the host tunnel (verified in the first goal).
- An RDP login locks the VM's console (VNC) session; accepted, VNC is not used for work.
- Unverified: the Python version of the CAE GUI process; the timer test settles it.
- C7 ALLAE/ALLIE has no pass limit; the criterion is that C6 reports it.
- The odb stores history values and times in single precision (relative error about
  6e-8), so the C6 comparison with the 8-digit .dat print uses rel 2e-7 and matches rows
  on time rounded to 6 decimals (found 2026-10-28).

## Ruled out
- The seminar model and a seminar repo (source: Enej, 2026-10-28).
- Choosing a forming process, collecting E-učilnica lab files, and finding Teaching
  Edition limits (source: Enej, 2026-10-28). Test models stay small.
- An unauthenticated exec socket, or any port listening on the VM's network interface.
- Writing Claude's changes to a separate .cae for Enej to reopen: the live bridge
  replaces it. Reading Enej's saved .cae and abaqus.rpy stays in scope.
- Abaqus/Explicit, unless a later goal needs it.

## Prediction
C7, frictionless upsetting with homogeneous deformation and plastic incompressibility:
F(h) = sigma_y * pi * R0^2 * H0 / h = 78.54 kN * H0 / h.
h/H0 = 0.9: 87.27 kN; 0.7: 112.20 kN; 0.5: 157.08 kN.
Elastic volume change is about (1 - 2 nu) sigma_y / E = 0.05 %, inside the 1 % band.
Abaqus is expected to report axisymmetric reaction forces as the total over 360 deg; a
result near F/(2 pi) means per radian, and the check uses the total.

## Log
- C4 (3) closed at 2 of 3 (2026-10-28): roller and strip pass; cylinder failed twice, each time on a
  derived number the advice did not check. The gap is in specs/backlog.md.
- C3 saved half, C4 (1), C4 (2), C5-C8 pass (critic reviews 1-5, 2026-10-28). C10 grep clean at 1f65cf3.
- 2026-10-28: closed by Enej with C1, C2, C3 live half and the C9 screenshot unrun; moved to backlog.
