# abaqus-mcp

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![Abaqus 2026](https://img.shields.io/badge/Abaqus-2026-orange) ![MCP stdio](https://img.shields.io/badge/MCP-stdio-green)

MCP server (stdio) on the Linux host. It runs Abaqus 2026 in a Windows VM over ssh/scp. The license server is reached over the university VPN.

## Install

- Windows VM: `./setup.sh` (see `setup.sh`), VPN: `bin/abaqus-vpn up|down|status`.
- Abaqus in the VM: `./setup.sh abaqus <media-dir> [--dry-run]` (calls `vm/install-abaqus.sh`; `<media-dir>/03_Abaqus2026/1/setup.exe`). Not part of the default `./setup.sh` run.
- The VM does not autostart after a host reboot: `virsh -c qemu:///system start abaqus-win`.
- `fs-abaqus` must be split-tunnel: `nmcli connection modify fs-abaqus ipv4.never-default yes`. A full tunnel cuts other internet traffic, including the Claude API.
- Server: `uv sync`.
- GUI over RDP (optional): `./setup.sh gui` once (enables RDP, adds the desktop shortcut "Abaqus CAE (mesa)"), then `bin/abaqus-gui`.
- Live bridge (optional): `./setup.sh live` installs the CAE plug-in into the VM account; restart CAE to load it.

## Configure

Copy `config.example.toml` to `config.local.toml` (git-ignored):

| key | default | meaning |
|---|---|---|
| `license_host`, `license_port` | none, 4085 | DSLS server, probed from the host |
| `ssh_host` | `abaqus-vm` | ssh alias of the VM |
| `work_host` | `~/abaqus-work` | host work dir, one sub-directory per job |
| `work_vm` | `C:\abaqus-work` | VM work dir |
| `abaqus_cmd` | `C:\Program Files\SIMULIA\Commands\abaqus.bat` | full path of the Abaqus launcher in the VM, used by every tool |
| `vpn_cmd` | `bin/abaqus-vpn` | run with `up` when the license port is closed |

`ABAQUS_MCP_CONFIG` overrides the config path.

## Register

```
claude mcp add abaqus -- uv run --directory "$(pwd)" abaqus-mcp   # run in the repo root
```

## Tools

A `job` is a name (a letter, then `[A-Za-z0-9_-]`); its files live in `<work_vm>\<job>`. Every tool returns JSON with `status`.

| tool | does |
|---|---|
| `license_check` | TCP probe of the license port; on failure `abaqus-vpn up` once and probe again; else `license server unreachable` (under 30 s) |
| `run_script(job, script_path)` | uploads a .py, runs `abaqus cae noGUI=`; exit code, bounded stdout/stderr, traceback |
| `submit_job(job, inp_file or cae_file, model, cpus, background)` | `abaqus job=... interactive`, or detached (`Win32_Process`) with a poll through `job_status`. `cae_file` is a host path (contains `/` or `\`, or starts with `~`), uploaded; a bare name is a file already in the VM job dir, never looked up in the server cwd |
| `job_status(job)` | `.sta`, `.msg`, `.lck`: status; per step increments done, attempts, cut-backs, equilibrium iterations, smallest and last time increment; `.msg` warnings grouped by type; last 5 errors |
| `odb_query(job, step, frame, variable, set_name, component)` | field output as JSON via `abaqus python`; the script writes the JSON to `_odb_query.json` in the job dir and the server fetches it; lists frames with frequency |
| `odb_history(job, step, region, outputs)` | history output of `<job>.odb`; without `outputs` the regions and output names per step, with `outputs` (e.g. `["RF2", "ALLIE"]`) `[time, value]` series of at most 200 points |
| `model_summary(job, cae_file, model, live)` | JSON summary of a .cae (parts, instances, sets, surfaces, materials, sections, steps, loads, BCs, interactions, mesh), fields in `docs/model_summary.schema.json`, under 20 kB with `omitted` counts; `cae_file` as in `submit_job`, default `<job>.cae`, `model` default the first; without `cae_file` and with a live CAE session it reads the open model, unsaved edits included |
| `model_views(job, cae_file, model, highlight, live)` | iso, front and top PNGs of the assembly (the first part if there are no instances), optionally one set or surface in red; copied to `<work_host>/<job>/<job>_views[_<highlight>]_{iso,front,top}.png` |
| `viewport_png(job, step_index, frame, variable)` | noGUI `printToFile`; PNG copied to `<work_host>/<job>/<job>_view.png` |
| `cae_live(script, timeout)` | runs Python in the open CAE GUI session (see Live session); returns output, a `result` variable, or the traceback; `no live CAE session` within 5 s without one |

`run_script`, `submit_job`, `model_summary`, `model_views` and `viewport_png` call `license_check` first. `run_script` and `cae_live` run arbitrary code in the VM.

## Live session

`bin/abaqus-gui` starts the VM if needed, brings the license VPN up and opens the VM desktop in `xfreerdp3` as user `abaqus` (password on stdin, never on a command line). Start "Abaqus CAE (mesa)" there; the VM has no 3D acceleration.

With the plug-in installed (`./setup.sh live`), CAE polls `C:\abaqus-work\live\inbox` every 0.5 s and runs each script in its kernel, so edits appear in the open model tree. A script waits until no dialog or procedure is active. Results go to `outbox`, every script is kept in `log`, and a heartbeat file marks the session alive. No network port is opened: the link is ssh and files.

## Skill

`skills/abaqus-modelling` is a Claude Code skill with method rules for Abaqus/Standard models (element choice, BCs, contact, convergence). Each rule cites an Abaqus 2026 documentation page, Bathe or Reddy, or is marked `[TBD]`. Link it into the user skill directory:

```
ln -s <repo>/skills/abaqus-modelling ~/.claude/skills/abaqus-modelling
```

## Test

- `uv run pytest`: unit tests against a fake transport, stdio `tools/list`, license timing.
- `ABAQUS_VM=1 uv run pytest -m vm`: smoke tests against the live VM (ssh/scp, VPN guard, detached process); no Abaqus needed. A test that brings the VPN up takes it down again.
- `ABAQUS_E2E=1 uv run pytest`: end-to-end on the real VM (needs Abaqus installed, VPN, `config.local.toml`): cantilever, upsetting (force against the closed form, cut-back run, history output against the `.dat`), `model_summary` and `model_views` on a saved .cae.
- `tests/advice/build.py [job ...]`: builds the .cae files used to test the skill.

Code adapted from MOBAI547800/abaqus-mcp-server (MIT): see `NOTICE`.
