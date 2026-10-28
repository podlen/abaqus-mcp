# Windows native: the MCP on a friend's Windows PC

Status: done, see Log; open items in backlog. Owner: Enej. Branch: 004-windows-native.

Goal: a friend on Windows with Abaqus installed and the university VPN connected runs the same MCP
server and skill natively, with no VM, no admin rights and no WSL, and gets it working from the
README without being fluent in Claude Code (source: Enej, 2026-10-28).

## Criteria
C1. Local transport. On Windows (`os.name == "nt"`) the server runs each command in a local
    Windows PowerShell 5.1 and copies files on the local disk; no ssh. Config `transport` =
    `local` or `ssh`, default `local` on Windows and `ssh` elsewhere. The eleven tools and their
    JSON are the same in both modes.
    check: unit tests for put/get and the transport choice; the E2E tests of C5 pass in local mode
    with the same asserts as in ssh mode (that is the "same JSON" rule).
C2. Abaqus found. On Windows, `abaqus_cmd` defaults to `abaqus` on PATH (`shutil.which`), else the
    first existing `abaqus.bat` under `C:\Program Files\SIMULIA\Commands` or `C:\SIMULIA\Commands`.
    check: unit tests mock `shutil.which` and the file lookup for all three branches; the doctor
    (C6) prints the path on the test machine.
C3. Licence. `license_host` comes from the config, else the first `host:port` line of
    `C:\ProgramData\DassaultSystemes\Licenses\DSLicSrv.txt`. With neither, the probe is skipped
    and `license_check` returns ok with `license: "not checked"`. `vpn_cmd` defaults to empty on
    Windows: no VPN start, the error hint says to connect the VPN.
    check: unit tests: a multi-line `DSLicSrv.txt` (comments and blank lines skipped), a missing
    file, config precedence, the skipped probe, the empty `vpn_cmd`.
C4. Setup without admin. `setup-windows.cmd` (double-click or terminal; works under the default
    Restricted execution policy) installs uv per user if missing (asks first), runs `uv sync`,
    copies the live plug-in to `%USERPROFILE%\abaqus_plugins\mcp_live` and creates the live
    folders, copies the skill to `%USERPROFILE%\.claude\skills\abaqus-modelling`, registers the MCP
    at user scope when `claude` is on PATH, and runs the doctor. A second run changes nothing it
    already did.
    check: run twice on the test machine through a scheduled task with `/RL LIMITED` in the
    console session (the VM user is an administrator; the limited token is the non-elevated case),
    output to a file; `whoami /groups` in that run shows `Medium Mandatory Level`. Second run: each
    item reads "already", copied files have the same SHA-256. Registration: a stub `claude.cmd` on
    PATH logs its arguments (no Claude Code in the VM). uv prompt: run once with uv off PATH and
    "y" piped in; if the download fails, setup prints the manual install link and stops.
C5. E2E on Windows. `ABAQUS_E2E=1 uv run pytest` passes in local mode on the test machine:
    cantilever, upsetting, summary. The live bridge answers `cae_live` with a CAE window open.
    check: pytest output; live: `ABAQUS_LIVE=1 uv run pytest tests/test_e2e_live.py` (a new file)
    with CAE started in the console session by a scheduled task (`/IT`); `abaqus` is logged on at
    the VM console (`query user`, 2026-10-28). If CAE cannot be started that way: UNKNOWN, needs Enej.
C6. Doctor. `uv run abaqus-mcp --check` prints one line per item (OS and transport, Abaqus
    command, licence probe, work folder writable, live plug-in installed, MCP registered) as
    OK/FAIL/INFO with a fix for each FAIL, and exits non-zero on a FAIL. FAIL: Abaqus command
    missing, work folder not writable, licence port closed. INFO: licence probe skipped (no host
    known), live plug-in missing, `claude` not found or MCP not registered.
    check: run on the test machine; run with a wrong `abaqus_cmd` shows FAIL and the fix.
C7. README for people new to Claude Code: a Windows section first (what you need, each step with
    what you should see, the first prompts to try, troubleshooting), then the Linux VM section.
    check: user judges (source: Enej, 2026-10-28: "more detailed and descriptive"); every command
    in the Windows section ran on the test machine (Log).
C8. Linux VM mode unchanged. check: `uv run pytest` (all ungated tests) passes on Linux; the
    cantilever E2E passes once over ssh at the end.

## Facts
- Test machine: the existing Windows 11 VM with Abaqus 2026, used as a stand-in for a friend's PC.
  Tests run inside it over ssh; the server under test uses the local transport. Its licence path
  goes through the host's split-tunnel VPN (source: Claude, 2026-10-28).
- Friends: Abaqus installed, `abaqus cae` starts from a terminal, VPN connected (source: Enej, 2026-10-28).
- No sudo and no installs on the Linux host for this work (source: Enej, 2026-10-28).
- `DSLicSrv.txt` holds `host:port` (seen in the VM install, 2026-10-28). Whether friends' installs
  write it: [TBD]; the doctor says to set `license_host` when no host is found.
- Windows 11 client default execution policy is Restricted; all scopes Undefined in the VM (2026-10-28).

## Ruled out
- Admin rights, WSL, a VM on Windows, changes to the friend's VPN (source: Enej, 2026-10-28).
- FlexLM licence detection (`abaquslm_license_file`): config `license_host` covers it [TBD if a friend needs it].

## Log
- 2026-10-28: LocalTransport, config defaults (DSLicSrv, find_abaqus), doctor, setup-windows.{cmd,ps1}, tests. Linux `uv run pytest`: 69 passed, 19 skipped. Doctor over ssh: all OK; a wrong abaqus_cmd gives FAIL plus fix, exit 1.
- 2026-10-28: setup-windows.cmd in the VM from "C:\Users\abaqus\My Tools\abaqus-mcp" (space in path, no config.local.toml): every step done, Claude Code LATER, doctor exit 0, about 24 s. uv was already installed.
- 2026-10-28: setup now also finds claude.exe/uv.exe in %USERPROFILE%\.local\bin (new terminal PATH lag) and writes a commented config.local.toml when missing. README rewritten with the Windows section first; decisions added.
- 2026-10-28: native E2E in the VM first hung in `abaqus cae noGUI` (child inherited the MCP stdin pipe): fixed with stdin=DEVNULL, test added. Native full run then: 71 passed, 5 failed (UTF-8 decode; awk/grep oracle in test_convergence), both fixed. Native unit run after: 60 passed, 29 skipped.
- 2026-10-28: C4 in the VM via `schtasks /RL LIMITED /IT` (whoami: `Medium Mandatory Level`): run 1 RC 0, config and uv sync done, stub `claude.cmd` logged `mcp remove -s user abaqus` and `mcp add -s user abaqus -- C:\Users\abaqus\.local\bin\uv.exe run --directory "C:\Users\abaqus\My Tools\abaqus-mcp" abaqus-mcp`; run 2 every item "already", 10 copied files with the same hash and mtime, stub not called. uv off PATH with "y" piped in: installer fetched uv 0.13.6, setup printed "done uv". The download-failure branch was not run. Fixes found: second run said "done" for uv sync (now `uv sync --check`); the doctor missed a BOM `.claude.json` (now utf-8-sig).
- 2026-10-28: C6: wrong `abaqus_cmd`, `work_vm = 'Q:\abaqus-work'` and `license_port = 1` gave three FAIL lines with fixes, exit 1. A TOML typo gave a raw traceback: config errors now exit with one line and a fix; `where abaqus` in PowerShell is Where-Object, the fix text now says `where.exe`.
- 2026-10-28: C5 live: CAE started in the console session by a scheduled task (`/IT`) loaded the plug-in but wrote no heartbeat: `FXSEL` is not in abaqusGui 2026 (NameError at load), now `MKUINT(id, SEL_TIMEOUT)`, timer probed in CAE. Then the second live script of a test stayed in the inbox: the dispatcher waited for `outbox/<id>.json`, which the MCP deletes once read; the kernel now also writes `log/<id>.json` as the done mark. Native `ABAQUS_LIVE=1 uv run pytest tests/test_e2e_live.py`: 2 passed. The live E2E from Linux over ssh was not run (cleanup of CAE in the VM blocked by the permission classifier).
- 2026-10-28: C8: Linux `uv run pytest`: 71 passed, 19 skipped; `ABAQUS_E2E=1 uv run pytest tests/test_e2e_cantilever.py` over ssh: 5 passed.
- 2026-10-28: critic review-1 (sonnet) PASS; review-2 (opus) FAIL on two Windows defects, both fixed: a local command past its timeout blocked until Abaqus exited (`subprocess.run` waits for pipes the children hold; now `taskkill /F /T`), and heartbeat ages printed `0,53` under sl-SI (checked in the VM; now `"$(...)"`, invariant culture). Native after the fixes: tests/test_windows.py 13 passed, cantilever E2E 5 passed, doctor reads a heartbeat age (negative too). Linux `uv run pytest`: 71 passed, 21 skipped.
