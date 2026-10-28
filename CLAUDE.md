# abaqus-mcp

- Read `.team/goal.md` (spec, Facts, Ruled out) first; finished goals are in `.team/archive/`.
- Abaqus 2026 Teaching Edition runs in the libvirt VM `abaqus-win` (`ssh abaqus-vm`, PowerShell 5.1).
  The VM does not autostart: `virsh -c qemu:///system start abaqus-win`.
- License: DSLS over the split-tunnel OpenVPN `fs-abaqus`, driven by `bin/abaqus-vpn up|down|status`.
- `abaqus cae noGUI` exits 0 on an uncaught exception, sends `print()` to `abaqus.rpy` and writes
  the traceback to stderr without its header. Detached jobs need `Win32_Process Create`.
- Use: university forming seminar, nonlinear plasticity, Abaqus/Standard (implicit) with small increments.
