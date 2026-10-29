# abaqus-mcp

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![Abaqus 2026](https://img.shields.io/badge/Abaqus-2026-orange) ![MCP stdio](https://img.shields.io/badge/MCP-stdio-green)

abaqus-mcp connects Claude Code to Abaqus. With it, you describe a model in plain words and Claude writes and runs the Abaqus Python scripts, submits jobs, reads convergence and results, renders the model, and edits the model in an open Abaqus/CAE window. A Claude Code skill, `skills/abaqus-modelling`, adds method advice for Abaqus/Standard models (elements, boundary conditions, contact, convergence).

It runs in two ways:

- **Windows (native)**: Abaqus is installed on your own Windows PC. Start at [Windows](#windows).
- **Linux (VM)**: Abaqus runs in a Windows virtual machine on a Linux PC. Start at [Linux](#linux).

Some words used below:

- **Claude Code** is Anthropic's AI assistant that runs in a terminal window and can run programs on your PC.
- An **MCP server** is a small program that gives Claude Code extra tools. This repository is one: its tools are listed under [Tools](#tools).
- A **terminal** is the text window where you type commands. On Windows it is called "Terminal" or "PowerShell" in the Start menu.

## Windows

Setup takes about 10 minutes. You need no administrator rights.

### What you need

- Windows 10 or 11 with Abaqus installed: Abaqus/CAE must open from the Start menu.
- The Abaqus licence: if your Abaqus uses a university licence server, connect the university VPN before you use Abaqus, as you would to start Abaqus/CAE by hand.
- A paid Claude plan (Pro, Max, Team or Enterprise) or an Anthropic Console account. The free claude.ai plan does not include Claude Code.
- Access to this repository: it is private on GitHub. Ask the owner to add your GitHub account, or ask for a ZIP file of it.
- An internet connection during setup (it downloads uv and Python packages).

### Step 1: install Claude Code

1. Open the Start menu, type `PowerShell` and open "Windows PowerShell". A window opens with a line such as `PS C:\Users\YourName>`.
2. Copy this line, paste it into the window (right-click pastes) and press Enter:

   ```powershell
   irm https://claude.ai/install.ps1 | iex
   ```

   It shows no progress while it downloads; wait until the prompt comes back.
3. Close the window and open a new PowerShell window. Type `claude --version` and press Enter. You should see a version number such as `2.1.211 (Claude Code)`. If you see "claude is not recognized", see [Troubleshooting](#troubleshooting).
4. Type `claude` and press Enter. A browser opens: log in with your Claude account. Then type `/exit` to close Claude Code again.

Claude Code also works without [Git for Windows](https://git-scm.com/downloads/win), but it is recommended: Claude Code then uses Git Bash for its commands, and you can download this repository with `git clone`.

Official instructions: [code.claude.com/docs/en/setup](https://code.claude.com/docs/en/setup).

### Step 2: get this repository

Put it in a folder you keep, for example `C:\Users\YourName\abaqus-mcp`. The folder name may contain spaces. Do not move the folder after setup: Claude Code remembers its path (run setup again after a move).

- **With Git** (gets updates easily): in PowerShell, run

  ```powershell
  cd $HOME
  git clone https://github.com/podlen/abaqus-mcp.git
  ```

  Git asks you to log in to GitHub the first time.
- **With a ZIP file**: on the GitHub page click **Code**, then **Download ZIP** (or use the ZIP the owner sent). Before you unpack it, right-click the ZIP file, choose **Properties**, tick **Unblock** at the bottom (if it is there) and click **OK**. Then right-click, **Extract All...**, and choose your user folder. The folder may be called `abaqus-mcp-main`; that name works too.

### Step 3: run the setup

1. Open the repository folder in File Explorer and double-click `setup-windows.cmd`. If Windows shows "Windows protected your PC", click **More info**, then **Run anyway**: the file is a plain text script and you can open it in Notepad to read it first.
2. A black window opens and prints one line per step. The first word of each line is the result:

   | word | meaning |
   |---|---|
   | `done` | the step did something now |
   | `already` | nothing to do, it was done before |
   | `LATER` | a step waits for something else (usually Claude Code is not installed yet) |
   | `FAIL` | the step failed; the line says why |
   | `STOP` | setup cannot go on; the line says what to do |

3. If uv is missing, setup asks `Install it for your user now? [Y/n]`. Press Enter to say yes. [uv](https://docs.astral.sh/uv/) installs Python and the packages this server needs, inside the repository folder only.
4. At the end setup runs a check of the whole installation. It looks like this:

   ```text
   INFO  machine          Windows 11, transport local
   OK    Abaqus command   C:\Program Files\SIMULIA\Commands\abaqus.BAT (Abaqus 2026)
   OK    licence          licence.server.example:4085 reachable
   OK    work folder      C:\abaqus-work writable
   OK    live plug-in     installed; no CAE window open now
   OK    skill            C:\Users\YourName\.claude\skills\abaqus-modelling
   OK    Claude Code      MCP server 'abaqus' registered (user scope)
   all checks passed
   ```

   `INFO` lines are not errors. Every `FAIL` line is followed by a `fix:` line: do what it says, then double-click `setup-windows.cmd` again. Running it again is always safe.
5. Press any key to close the window.

What setup changed on your PC:

- `.venv` (Python packages) and `config.local.toml` (your settings, all commented out at first) inside the repository folder;
- uv in `%USERPROFILE%\.local\bin`, if you let it install uv;
- the live plug-in in `%USERPROFILE%\abaqus_plugins\mcp_live`, which Abaqus/CAE loads at start;
- the skill in `%USERPROFILE%\.claude\skills\abaqus-modelling`;
- the work folder `C:\abaqus-work`, where Abaqus runs the jobs;
- the entry `abaqus` in the Claude Code settings (`%USERPROFILE%\.claude.json`).

### Step 4: first session

1. Make a folder for your analysis, for example `C:\Users\YourName\fem\cantilever`. It must be inside your user folder. Model files you already have (`.cae`, `.inp`) can go there.
2. Open a new PowerShell window and go to that folder, then start Claude Code:

   ```powershell
   mkdir $HOME\fem\cantilever
   cd $HOME\fem\cantilever
   claude
   ```

   (`mkdir` only the first time.)

3. Type `/mcp` and press Enter. You should see `abaqus` with the status connected. Press Esc.
4. Ask in plain words. Claude first asks which folder the project lives in (or uses the one you name). Prompts to try:
   - `Check that the Abaqus licence is reachable.`
   - `Project folder is C:\Users\YourName\fem\cantilever. Build a steel cantilever, 200 x 20 x 10 mm, fixed at one end, 100 N down at the free end, C3D8R mesh, run it and compare the tip deflection with beam theory.`
   - `Open model.cae in this folder, tell me what the model contains and show me a picture of it.`
   - `The job upsetting stopped converging. Find out why and suggest a fix.`
5. Claude asks before it runs a tool the first time. Read what it wants to do and answer **Yes**. The prompt also offers to stop asking for that tool; choose it once you trust the tool.

Results land in the project folder, one sub-folder per job (`<project>\<job>\`): the `.odb`, `.sta`, `.msg`, pictures and JSON results. Abaqus itself works in `C:\abaqus-work\...`; the server copies the files back.

### Working in an open CAE window

Claude can also change the model in an Abaqus/CAE window you have open, and you see each change in the model tree.

1. Start Abaqus/CAE from the Start menu (or with `abaqus cae` in a terminal). Setup installed a plug-in that CAE loads at start; if CAE was open during setup, close it and start it again.
2. In Claude Code, ask for example: `In the open CAE window, add a 5 mm fillet to the part Bracket and remesh it.`
3. Claude sends a script to the window. A script waits while a dialog is open in CAE, so close dialogs when Claude works.

### Update

With Git: in PowerShell, go to the repository folder and run `git pull`. With a ZIP: download a new ZIP and unpack it over the old folder (keep your `config.local.toml`). Then double-click `setup-windows.cmd` again and start a new Claude Code session.

### Troubleshooting

To run the check again without setup: in PowerShell, in the repository folder, run `uv run abaqus-mcp --check`.

- **`claude` (or `uv`) is not recognized**: close every PowerShell window and open a new one; installers change the PATH only for new windows. If it still fails, sign out of Windows and in again.
- **`FAIL Abaqus command ... not found`**: setup did not find Abaqus. In PowerShell run `where.exe abaqus`. If it prints a path, open `config.local.toml` (`notepad config.local.toml` in the repository folder), remove the `#` before `abaqus_cmd` and put that path between the single quotes. If it prints nothing, look in the folder where Abaqus is installed for `Commands\abaqus.bat`. Some Learning Edition installs name the command differently: [TBD].
- **`FAIL licence ... not reachable`**: connect the university VPN and run the check again. If the VPN is connected and it still fails, ask whoever gave you the licence for the server name and port, then set `license_host` and `license_port` in `config.local.toml`.
- **`INFO licence no licence host known`**: setup found no licence server in `C:\ProgramData\DassaultSystemes\Licenses\DSLicSrv.txt`. That is fine when Abaqus starts without a licence server. If jobs fail with a licence error, set `license_host` as above.
- **`FAIL work folder`**: you cannot write `C:\abaqus-work`. Set `work_vm` in `config.local.toml` to a folder you can write, with no spaces or accented letters in its path (for example `'D:\abaqus-work'`), then run setup again. Abaqus fails on paths with spaces or accents, so the server keeps its work folder apart from your project folder.
- **`/mcp` shows abaqus as failed, or not at all**: run setup again and read the `Claude Code` line. Then quit Claude Code (`/exit`) and start it again. `claude mcp list` (run outside the repository folder) lists the registered servers.
- **"Windows protected your PC" or "The publisher could not be verified"**: Windows marks files from the internet. Unblock the ZIP before unpacking (Step 2), or click **More info**, **Run anyway**.
- **Setup window closes at once**: open PowerShell in the repository folder (in File Explorer, click the address bar, type `powershell`, press Enter) and run `.\setup-windows.cmd` to read the output.

### Settings

`config.local.toml` in the repository folder. Every key is optional on Windows; remove the `#` before a line to use it. Text values go in quotes; for Windows paths use single quotes so the backslashes stay as typed.

| key | default on Windows | meaning |
|---|---|---|
| `abaqus_cmd` | `abaqus` found on PATH, else `C:\Program Files\SIMULIA\Commands\abaqus.bat`, else `C:\SIMULIA\Commands\abaqus.bat` | the Abaqus command every tool runs |
| `license_host`, `license_port` | the first `host:port` line of `C:\ProgramData\DassaultSystemes\Licenses\DSLicSrv.txt` | licence server the server checks before a job; with none known the check is skipped |
| `work_vm` | `C:\abaqus-work` | folder where Abaqus runs; each project gets a sub-folder. ASCII letters, no spaces |
| `state_dir` | `%LOCALAPPDATA%\abaqus-mcp` | scratch files of the server |
| `transport` | `local` | `local` runs Abaqus on this PC; `ssh` is the Linux VM mode |
| `print_cap`, `node_limit` | 4000, 0 | as in the Linux table below |

In the repository folder, `uv run python -m abaqus_mcp.config --print` shows the values in use.

### Uninstall (Windows)

In PowerShell:

```powershell
claude mcp remove -s user abaqus
Remove-Item -Recurse "$env:USERPROFILE\.claude\skills\abaqus-modelling", "$env:USERPROFILE\abaqus_plugins\mcp_live"
```

Then delete the repository folder (with `.venv` and `config.local.toml` in it), and `C:\abaqus-work` if you do not need the job files there.

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

These tools are the same on Windows and Linux; on Windows "the VM" below means your own PC, and `C:\abaqus-work` is `work_vm`.

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

On Windows: start Abaqus/CAE yourself; see [Working in an open CAE window](#working-in-an-open-cae-window). The rest of this section is the Linux VM.


`bin/abaqus-gui` starts the VM if needed, brings the license VPN up and opens the VM desktop in `xfreerdp3` through 127.0.0.1:`rdp_port` as user `abaqus` (password on stdin, never on a command line). Start "Abaqus CAE (mesa)" there; the VM has no 3D acceleration.

With the plug-in installed (`./setup.sh live`), CAE polls `C:\abaqus-work\live\inbox` every 0.5 s and runs each script in its kernel, so edits appear in the open model tree. A script waits until no dialog or procedure is active. Results go to `outbox`, every script is kept in `log`, and a heartbeat file marks the session alive. No network port is opened: the link is ssh and files.

## Uninstall (Linux)

`./setup.sh uninstall` shows the size of `state_dir` (`du -sh`), asks yes or no, then stops and undefines the domain (`undefine --nvram`) and deletes `state_dir`. It refuses when `state_dir` has no setup marker (`.abaqus-mcp-setup`) or is `$HOME`, `/`, the repo or a parent of the repo. Reused ISOs in `iso_dir`, the repo and `config.local.toml` stay. Remove the registration with `claude mcp remove -s user abaqus` and the skill link with `rm ~/.claude/skills/abaqus-modelling`.

## Skill

`skills/abaqus-modelling` is a Claude Code skill with method rules for Abaqus/Standard models (element choice, BCs, contact, convergence). Each rule cites an Abaqus 2026 documentation page, Bathe or Reddy, or is marked `[TBD]`. On Windows, `setup-windows.cmd` copies it to `%USERPROFILE%\.claude\skills` (run setup again after an update). On Linux, link it into the user skill directory:

```
ln -s <repo>/skills/abaqus-modelling ~/.claude/skills/abaqus-modelling
```

## Test

- `uv run pytest`: unit tests against a fake transport, stdio `tools/list`, license timing.
- `ABAQUS_VM=1 uv run pytest -m vm`: smoke tests against the live VM (ssh/scp, VPN guard, detached process); no Abaqus needed. A test that brings the VPN up takes it down again.
- `ABAQUS_E2E=1 uv run pytest`: end-to-end on the real VM (needs Abaqus installed, VPN, `config.local.toml`; each test uses a temporary project directory under `$HOME`): cantilever, upsetting (force against the closed form, cut-back run, history output against the `.dat`), `model_summary` and `model_views` on a saved .cae.
- Windows: `uv run pytest` runs the same unit tests plus the PowerShell ones; `$env:ABAQUS_E2E="1"; uv run pytest` runs the end-to-end tests on the local Abaqus; `$env:ABAQUS_LIVE="1"; uv run pytest tests/test_e2e_live.py` needs an open CAE window with the plug-in loaded.
- `tests/advice/build.py [job ...]`: builds the .cae files used to test the skill.

Code adapted from MOBAI547800/abaqus-mcp-server (MIT): see `NOTICE`.
