# abaqus-mcp

MCP server (stdio) on the Linux host. It runs Abaqus 2026 in a Windows VM over ssh/scp. The license server is reached over the university VPN.

## Install

- Windows VM: `./setup.sh` (see `setup.sh`), VPN: `bin/abaqus-vpn up|down|status`.
- Abaqus in the VM: `./setup.sh abaqus <media-dir> [--dry-run]` (calls `vm/install-abaqus.sh`; `<media-dir>/03_Abaqus2026/1/setup.exe`). Not part of the default `./setup.sh` run.
- The VM does not autostart after a host reboot: `virsh -c qemu:///system start abaqus-win`.
- `fs-abaqus` must be split-tunnel: `nmcli connection modify fs-abaqus ipv4.never-default yes`. A full tunnel cuts other internet traffic, including the Claude API.
- Server: `uv sync`.

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
| `job_status(job)` | `.sta`, `.msg`, `.lck`: status, increment, `.msg` errors and warnings |
| `odb_query(job, step, frame, variable, set_name, component)` | field output as JSON via `abaqus python`; the script writes the JSON to `_odb_query.json` in the job dir and the server fetches it; lists frames with frequency |
| `model_info(job, cae_file)` | parts, sets, steps, materials of a .cae (JSON by file, `cae_file` as in `submit_job`; default `<job>.cae`) |
| `viewport_png(job, step_index, frame, variable)` | noGUI `printToFile`; PNG copied to `<work_host>/<job>/<job>_view.png` |

`run_script`, `submit_job`, `model_info` and `viewport_png` call `license_check` first. `run_script` runs arbitrary code in the VM.

## Test

- `uv run pytest`: unit tests against a fake transport, stdio `tools/list`, license timing.
- `ABAQUS_VM=1 uv run pytest -m vm`: smoke tests against the live VM (ssh/scp, VPN guard, detached process); no Abaqus needed. A test that brings the VPN up takes it down again.
- `ABAQUS_E2E=1 uv run pytest tests/test_e2e_cantilever.py`: cantilever on the real VM (needs Abaqus installed, VPN, `config.local.toml`).

Code adapted from MOBAI547800/abaqus-mcp-server (MIT): see `NOTICE`.
