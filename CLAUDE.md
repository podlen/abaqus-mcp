# abaqus-mcp

- Read the active spec in `specs/` first (`.critic/spec.md` links to it); flow in `specs/README.md`.
  Machine-local facts: `.team/local.md` (git-ignored, may be absent).
- Ask the user for the project's analysis directory before starting a project.
- Abaqus 2026 Teaching Edition runs in the libvirt VM `abaqus-win` (`ssh abaqus-vm`, PowerShell 5.1).
  The VM does not autostart: `virsh -c qemu:///system start abaqus-win`.
- License: DSLS over the split-tunnel OpenVPN `fs-abaqus`, driven by `bin/abaqus-vpn up|down|status`.
- `abaqus cae noGUI` exits 0 on an uncaught exception, sends `print()` to `abaqus.rpy` and writes
  the traceback to stderr without its header. Detached jobs need `Win32_Process Create`.
- Use: university forming seminar, nonlinear plasticity, Abaqus/Standard (implicit) with small increments.
