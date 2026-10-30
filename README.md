# abaqus-mcp

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![Abaqus 2026](https://img.shields.io/badge/Abaqus-2026-orange) ![MCP stdio](https://img.shields.io/badge/MCP-stdio-green)

abaqus-mcp connects Claude Code to Abaqus. With it, you describe a model in plain words and Claude writes and runs the Abaqus Python scripts, submits jobs, reads convergence and results, renders the model, and edits the model in an open Abaqus/CAE window. A Claude Code skill, `skills/abaqus-modelling`, adds method advice for Abaqus/Standard models (elements, boundary conditions, contact, convergence).

This is the `windows` branch: Abaqus is installed on your own Windows PC. For Abaqus in a Windows virtual machine on a Linux PC, use the [`linux` branch](https://github.com/podlen/abaqus-mcp/tree/linux).

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
  git clone -b windows https://github.com/podlen/abaqus-mcp.git
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

## Tools

In the tool table, "the VM" means your own PC, and `C:\abaqus-work` is `work_vm`.

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

Start Abaqus/CAE yourself; see [Working in an open CAE window](#working-in-an-open-cae-window).

With the plug-in installed (by `setup-windows.cmd`), CAE polls `C:\abaqus-work\live\inbox` every 0.5 s and runs each script in its kernel, so edits appear in the open model tree. A script waits until no dialog or procedure is active. Results go to `outbox`, every script is kept in `log`, and a heartbeat file marks the session alive. No network port is opened: the link is ssh and files.

## Skill

`skills/abaqus-modelling` is a Claude Code skill with method rules for Abaqus/Standard models (element choice, BCs, contact, convergence). Each rule cites an Abaqus 2026 documentation page, Bathe or Reddy, or is marked `[TBD]`. `setup-windows.cmd` copies it to `%USERPROFILE%\.claude\skills` (run setup again after an update).

## Test

- `uv run pytest`: unit tests against a fake transport, plus the PowerShell ones; `$env:ABAQUS_E2E="1"; uv run pytest` runs the end-to-end tests on the local Abaqus; `$env:ABAQUS_LIVE="1"; uv run pytest tests/test_e2e_live.py` needs an open CAE window with the plug-in loaded.
- `tests/advice/build.py [job ...]`: builds the .cae files used to test the skill.

Code adapted from MOBAI547800/abaqus-mcp-server (MIT): see `NOTICE`.
