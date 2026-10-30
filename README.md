# abaqus-mcp

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![Abaqus 2026](https://img.shields.io/badge/Abaqus-2026-orange) ![MCP stdio](https://img.shields.io/badge/MCP-stdio-green)

abaqus-mcp connects Claude Code to Abaqus. With it, you describe a model in plain words and Claude writes and runs the Abaqus Python scripts, submits jobs, reads convergence and results, renders the model, and edits the model in an open Abaqus/CAE window. A Claude Code skill, `skills/abaqus-modelling`, adds method advice for Abaqus/Standard models (elements, boundary conditions, contact, convergence).

This is the `linux` branch: Abaqus runs in a Windows virtual machine on a Linux PC. For Abaqus installed on your own Windows PC, use the [`windows` branch](https://github.com/podlen/abaqus-mcp/tree/windows).

Some words used below:

- **Claude Code** is Anthropic's AI assistant that runs in a terminal window and can run programs on your PC.
- An **MCP server** is a small program that gives Claude Code extra tools. This repository is one: its tools are listed under [Tools](#tools).
- A **terminal** is the text window where you type commands.

## Linux

abaqus-mcp on Linux runs Abaqus 2026 in a Windows 11 evaluation VM that `./setup.sh` builds on your machine; the MCP server sends scripts and jobs to it over SSH. It is for a Linux user with an own Abaqus licence (DSLS license server) who reaches that server over a VPN. The VM runs in your user-session libvirt; the build touches nothing outside one state directory and libvirt's own per-user folders.

### Install

Each step names the command and what to check afterwards.

1. Host packages: libvirt with the passt backend, qemu, passt, virt-install, xorriso, edk2-ovmf, curl, openssh, openssl, [uv](https://docs.astral.sh/uv/). Tested with libvirt 12.8.0, qemu-base 11.1.2, virt-install 5.1.0; minimum versions: [TBD]. Arch: `sudo pacman -S libvirt qemu-base virt-install passt libisoburn edk2-ovmf`. Start libvirt's user daemon so that `virsh -c qemu:///session list` runs. No sudo is needed after this step. `./setup.sh deps` checks `virsh -c qemu:///session` and `command -v passt` and stops with the package names.
2. VPN: create a NetworkManager connection to your university VPN, split-tunnel (`nmcli connection modify <name> ipv4.never-default yes`; a full tunnel cuts other internet traffic, including the Claude API). Put its name in `vpn_connection` (default `fs-abaqus`). `bin/abaqus-vpn up|down|status` wraps it.
3. Config: `uv sync`, then `cp config.example.toml config.local.toml` (git-ignored) and set at least `license_host`.
4. Build the VM: `./setup.sh`. It downloads about 6 GB (Windows 11 Enterprise evaluation ISO, virtio-win ISO) and the unattended install takes about 20 to 40 minutes. Every stage is idempotent; `./setup.sh --list` shows them, `./setup.sh <stage>...` runs some. The last stage, `wait`, ends when SSH answers. Check: `ssh -F ~/.local/share/abaqus-mcp/ssh_config abaqus-vm cmd /c ver` prints a Windows version (use your `state_dir` if you changed it).
5. Abaqus in the VM: `./setup.sh abaqus <media-dir>`; `<media-dir>/03_Abaqus2026/1/setup.exe` must exist (`--dry-run` prints the steps). It is not part of the default run.
6. Optional: `./setup.sh gui` once (enables RDP, adds the desktop shortcut "Abaqus CAE (mesa)"), then `bin/abaqus-gui` opens the VM desktop. `./setup.sh live` installs the live-bridge plug-in; restart CAE to load it.
7. Register the server (run in the repo root): `claude mcp add -s user abaqus -- uv run --directory "$(pwd)" abaqus-mcp`.
8. Link the skill: `ln -s "$(pwd)/skills/abaqus-modelling" ~/.claude/skills/abaqus-modelling`.

The build writes only to `state_dir` (default `~/.local/share/abaqus-mcp`: disk image, ISOs or links to reused ones, answer ISO, SSH key, `ssh_config`, admin password, a marker file, scratch files) and to libvirt's per-user folders (`~/.config/libvirt/`, `~/.local/share/libvirt/`, `~/.cache/libvirt/`). `~/.ssh` and the system libvirt are not touched. The domain `vm_name` (default `abaqus-mcp`) has passt networking; the host reaches the guest only through forwards on 127.0.0.1: `ssh_port` (guest SSH) and `rdp_port` (guest RDP). The VM does not autostart after a host reboot: `virsh -c qemu:///session start abaqus-mcp` (or run `bin/abaqus-gui`).

#### Windows evaluation

The VM runs a 90-day Windows 11 Enterprise evaluation. `vm/fl-setup.ps1` runs `slmgr /rearm` at first logon. Read the end date: `ssh -F ~/.local/share/abaqus-mcp/ssh_config abaqus-vm "cscript //nologo C:\Windows\System32\slmgr.vbs /xpr"`. When it nears, rearm with `slmgr.vbs /rearm` in the VM and reboot it (rearms allowed: [TBD]), or rebuild: `./setup.sh uninstall`, then `./setup.sh` and `./setup.sh abaqus <media-dir>`.

### Configure

`config.local.toml` (git-ignored; `ABAQUS_MCP_CONFIG` overrides the path). Defaults live in `src/abaqus_mcp/config.py`; `uv run python -m abaqus_mcp.config --print` shows the resolved values as shell lines.

| key | default | meaning |
|---|---|---|
| `license_host`, `license_port` | none, 4085 | DSLS server, probed from the host and reached by the VM through the host's VPN |
| `vm_name` | `abaqus-mcp` | libvirt domain in `qemu:///session` |
| `ram_mb`, `vcpus`, `disk_gb` | 8192, 6, 80 | VM size |
| `ssh_port`, `rdp_port` | 2222, 3390 | host ports on 127.0.0.1, forwarded to the guest's 22 and 3389 |
| `state_dir` | `~/.local/share/abaqus-mcp` | everything `setup.sh` creates |
| `iso_dir` | none | optional: `win11-eval.iso` and `virtio-win.iso` found here are linked, not downloaded; `uninstall` leaves them |
| `vpn_connection` | `fs-abaqus` | NetworkManager connection used by `bin/abaqus-vpn` |
| `ssh_host` | `abaqus-vm` | Host alias in `<state_dir>/ssh_config` |
| `work_vm` | `C:\abaqus-work` | VM root; each project gets a sub-directory |
| `abaqus_cmd` | `C:\Program Files\SIMULIA\Commands\abaqus.bat` | full path of the Abaqus launcher in the VM, used by every tool |
| `vpn_cmd` | `bin/abaqus-vpn` | run with `up` when the license port is closed |
| `transport` | `ssh` | `ssh` runs every command in the VM; `local` is the native Windows mode |
| `print_cap` | 4000 | characters of `print_output`, `stdout` and `stderr` that `run_script` returns |
| `node_limit` | 0 (off) | `model_summary` adds `mesh.warning` above this node count; the Teaching Edition limit is 250000 |

### Use

1. Start the VPN if the licence server needs it: `bin/abaqus-vpn up` (`license_check` also does this once).
2. Start Claude Code in any directory. The first tool call of a project is `set_project(path)`: the analysis directory, either with existing model files or a new location under `$HOME`. The skill asks for it as its step 0.
3. Ask Claude to build, run and check a model. Results land in `<project>/<job>/`.
4. For the CAE window: `bin/abaqus-gui`, start "Abaqus CAE (mesa)" in the VM desktop, then Claude can use `cae_live`, and `model_summary` and `model_views` read the open model.

## Tools

A `job` is a name (a letter, then `[A-Za-z0-9_-]`); its files live in `<project>/<job>/` on the host and in `C:\abaqus-work\<slug>-<hash>\<job>` in the VM (`slug`: the project directory name reduced to `[A-Za-z0-9_-]`, `hash`: first 8 hex of the sha1 of its resolved path). Every tool returns JSON with `status`. A bare file name given to `run_script` or `submit_job` is looked up in the project directory.

| tool | does |
|---|---|
| `set_project(path)` | sets the analysis directory of the session (under `$HOME`, symlinks followed, created if new); a second call switches projects. Job tools return `no project: call set_project` before the first call |
| `license_check` | TCP probe of the license port; on failure `abaqus-vpn up` once and probe again; else `license server unreachable` (under 30 s). With an empty `vpn_cmd` (the Windows default) it starts no VPN and asks you to connect it; with no known licence host it returns `not checked` |
| `run_script(job, script_path, inputs, outputs)` | uploads the .py, the `inputs` files and the `abqmcp` helper module, runs the script under `abaqus cae noGUI=` in a fresh namespace with the CAE modules loaded, copies `outputs` to `<project>/<job>/` (`fetched`, `missing`); `print_output` and `stdout` with repeated lines collapsed and cut to the last `print_cap` characters; on failure also stderr and the traceback |
| `submit_job(job, inp_file or cae_file, model, cpus, background)` | `abaqus job=... interactive`, or detached (`Win32_Process`) with a poll through `job_status`. `cae_file` is a host path (contains `/` or `\`, or starts with `~`), uploaded; a bare name is a file already in the VM job dir, never looked up in the server cwd |
| `job_status(job)` | `.sta`, `.msg`, `.lck`: status; per step increments done, attempts, cut-backs, equilibrium iterations, smallest and last time increment; `.msg` warnings grouped by type; last 5 errors |
| `odb_query(job, step, frame, variable, set_name, component)` | field output as JSON via `abaqus python`; the script writes the JSON to `_odb_query.json` in the job dir and the server fetches it; lists frames with frequency |
| `odb_history(job, step, region, outputs)` | history output of `<job>.odb`; without `outputs` the regions and output names per step, with `outputs` (e.g. `["RF2", "ALLIE"]`) `[time, value]` series of at most 200 points |
| `model_summary(job, cae_file, model, live, only)` | JSON summary of a .cae (parts, instances, sets, surfaces, materials, sections, steps, loads, BCs, interactions, mesh), fields in `docs/model_summary.schema.json`, under 20 kB with `omitted` counts; `cae_file` as in `submit_job`, default `<job>.cae`, `model` default the first; without `cae_file` and with a live CAE session it reads the open model, unsaved edits included; `only` keeps the named top-level keys; `mesh.techniques` counts cells per assigned mesh control, `mesh.warning` appears above `node_limit` |
| `model_views(job, cae_file, model, highlight, views, size, live)` | PNGs (default 900 x 600; iso, front and top) of the assembly (the first part if there are no instances), optionally one set or surface in red, copied to `<project>/<job>/<job>_views[_<highlight>]_<view>.png`; a list of highlights gives one iso PNG per name from one CAE run, keyed `<name>:<view>` |
| `viewport_png(job, step_index, frame, variable)` | noGUI `printToFile`; PNG copied to `<project>/<job>/<job>_view.png` |
| `cae_live(script, timeout)` | runs Python in the open CAE GUI session (see Live session); returns output, a `result` variable, or the traceback; `no live CAE session` within 5 s without one |

`run_script`, `submit_job`, `model_summary`, `model_views` and `viewport_png` call `license_check` first. `run_script` and `cae_live` run arbitrary code in the VM.

## Live session


`bin/abaqus-gui` starts the VM if needed, brings the license VPN up and opens the VM desktop in `xfreerdp3` through 127.0.0.1:`rdp_port` as user `abaqus` (password on stdin, never on a command line). Start "Abaqus CAE (mesa)" there; the VM has no 3D acceleration.

With the plug-in installed (`./setup.sh live`), CAE polls `C:\abaqus-work\live\inbox` every 0.5 s and runs each script in its kernel, so edits appear in the open model tree. A script waits until no dialog or procedure is active. Results go to `outbox`, every script is kept in `log`, and a heartbeat file marks the session alive. No network port is opened: the link is ssh and files.

## Uninstall (Linux)

`./setup.sh uninstall` shows the size of `state_dir` (`du -sh`), asks yes or no, then stops and undefines the domain (`undefine --nvram`) and deletes `state_dir`. It refuses when `state_dir` has no setup marker (`.abaqus-mcp-setup`) or is `$HOME`, `/`, the repo or a parent of the repo. Reused ISOs in `iso_dir`, the repo and `config.local.toml` stay. Remove the registration with `claude mcp remove -s user abaqus` and the skill link with `rm ~/.claude/skills/abaqus-modelling`.

## Skill

`skills/abaqus-modelling` is a Claude Code skill with method rules for Abaqus/Standard models (element choice, BCs, contact, convergence). Each rule cites an Abaqus 2026 documentation page, Bathe or Reddy, or is marked `[TBD]`. Link it into the user skill directory:

```
ln -s <repo>/skills/abaqus-modelling ~/.claude/skills/abaqus-modelling
```

## Test

- `uv run pytest`: unit tests against a fake transport, stdio `tools/list`, license timing.
- `ABAQUS_VM=1 uv run pytest -m vm`: smoke tests against the live VM (ssh/scp, VPN guard, detached process); no Abaqus needed. A test that brings the VPN up takes it down again.
- `ABAQUS_E2E=1 uv run pytest`: end-to-end on the real VM (needs Abaqus installed, VPN, `config.local.toml`; each test uses a temporary project directory under `$HOME`): cantilever, upsetting (force against the closed form, cut-back run, history output against the `.dat`), `model_summary` and `model_views` on a saved .cae.
- `tests/advice/build.py [job ...]`: builds the .cae files used to test the skill.

Code adapted from MOBAI547800/abaqus-mcp-server (MIT): see `NOTICE`.
