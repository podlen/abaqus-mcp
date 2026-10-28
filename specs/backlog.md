# Backlog

Gaps found while working, not yet in a spec.

- Advice agents state derived numbers (error at a mesh size, model-size ratios) without checking
  them; the cylinder held-out advice failed twice on one (002 Log). Candidate skill rule: every
  number in the advice comes from the workflow step-5 hand calc or carries [TBD].
- Advice tags sometimes point at a neighbouring rule (C10 vs C7, G2 vs G1); the skill's tag layout
  may need one tag per rule.
- M13 element sizing at a stress peak has no source; stays [TBD].
- Kt handbook source (Peterson, Pilkey or Roark) for the plate-with-hole check.
- C2 idle detection: the AFXProcedure counter is unproven with a dialog open (004 ran it idle only); a stuck counter blocks every live script.
- Held-out models should avoid physics with a ready Abaqus benchmark page (Hertz has one).
- 002 unrun checks, need a person at the screen: C1 (CAE visual and `ps`), C2 (a)-(d) via
  live_checks.py, C9 CAE screenshot without IP, host, user or password.
- 003: a real `./setup.sh uninstall` run (C6); the parent-of-repo refusal has no own test.
- 003 C8: a second user runs the README from clone to uninstall on an own Linux machine.
- README [TBD]s: minimum libvirt version for passt `portForward`; Windows evaluation rearm count.
- 004: the live E2E from Linux over ssh (`ABAQUS_LIVE=1 uv run pytest tests/test_e2e_live.py`) with CAE open in the VM; native run passed.
- 004: setup-windows uv download-failure branch (prints the manual link, exit 1) not run.
- 004: whether friends' installs write `DSLicSrv.txt` and name the launcher `abaqus` (Learning Edition): [TBD].
- 004: the tools never ran under a non-admin token (E2E ran over ssh as an admin): creating `C:\abaqus-work` and `Win32_Process.Create` for detached jobs as a standard user are unproven.
