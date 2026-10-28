# Prior art: Abaqus MCP servers

Searched GitHub 2026-10-27 (`gh search repos` for "abaqus mcp", "abaqus model context protocol", "abaqus mcp server"). About 25 repos found. Most are forks or copies of Cai-aa/abaqus-mcp. Eight were read: seven for Abaqus, one for ANSYS. Clones are in the session scratchpad, nothing was executed.

Not read: Flyme-wang/wmw-abaqus-mcp (multi-port fork of the socket bridge), YangCinto/abaqus-mcp-opencode (fork of Cai-aa with a noGUI autostart script and no tests), LuckYang1/abaqus-mcp, Kongho129/abaqus-mcp, pureSaviour/abaqus-mcp.

## Facts

| | Cai-aa/abaqus-mcp | yezg9920-kely/abaqus-mcp | jianzhichun/abaqus-mcp-server | rutwikg/abaqus-mcp | MOBAI547800/abaqus-mcp-server | TutuBarry/abaqus-mcp-pro | knewnothing-git/ansys-mcp-server |
|---|---|---|---|---|---|---|---|
| License | MIT | MIT | MIT | AGPL-3.0 | MIT | MIT | MIT |
| Last commit | 2026-10-26 | 2026-07-30 | 2025-05-27 | 2026-09-17 | 2026-07-23 | 2026-10-14 | 2025-09-14 |
| Stars | 311 | 0 | 108 | 3 | 0 | 6 | 71 |
| Link to Abaqus | socket server inside CAE (plugin, `exec`) | same, token-less, 127.0.0.1 | pywinauto GUI scripting | `abaqus job=` and `abaqus cae -noGUI` subprocess, `abaqus python` for ODB | `abaqus` subprocess (`cae noGUI=`, `job=`, `python`) | socket, file IPC or noGUI agent inside CAE | PyMAPDL / PyFluent sessions |
| Tools | check_abaqus_connection, execute_script, get_model_info, list_jobs, submit_job, get_odb_info, get_viewport_image, ping | adds run_python, set_workdir, monitor_job_status, inspect_odb, capture_viewport | execute_script, get_abaqus_message_log | 13+ (run_simulation, autocorrect_simulation, get_job_status, read_job_file, build_model, get_results, check_validity, sweeps) | 11 (check_environment, run_script, generate_script, submit_job, job_status, read_job_logs, extract_odb_summary/field/history, clean_job, validate_workspace) | 135 tools, 74 resources, 13 prompts | create_fluent_session, create_mapdl_session, run_mapdl_commands, read_ansys_file |
| Results/errors | JSON string; `Error: ...` string | dict plus markdown-formatted error, tail/grep of .msg/.sta | scraped text from the GUI message area | text report built from parsed .sta/.msg/.dat; results from `extract_odb.py` | text; ODB scripts print JSON; log parser classifies .sta | structured error format, solver diagnosis | text, session errors as strings |
| OS | any host with CAE running, Windows plugin paths | same | Windows only | Windows or Linux, Abaqus 2022 stated | Windows tested (`cmd.exe /c call`), Abaqus 2025 | Windows (validated on Abaqus 2026) | any |
| Tests | yes, 1 file, mocked Abaqus API (viewport only) | no tests dir | yes, 282 lines, all GUI mocked | yes, 7 unit files plus fixtures (parsers, fix rules, spec) | yes, 85 tests: unit, mocked CLI, MCP protocol | yes, 391 Python tests plus 43 frontend; regressions from real 2026 runs | 1 file |

## Ratings (1 to 5)

| Repo | Fit | Code quality | Error handling | Safety | Tests | Sum |
|---|---|---|---|---|---|---|
| MOBAI547800/abaqus-mcp-server | 5 | 4 | 4 | 4 | 4 | 21 |
| rutwikg/abaqus-mcp | 4 | 4 | 4 | 3 | 3 | 18 |
| TutuBarry/abaqus-mcp-pro | 2 | 3 | 4 | 3 | 4 | 16 |
| Cai-aa/abaqus-mcp | 2 | 3 | 2 | 2 | 2 | 11 |
| yezg9920-kely/abaqus-mcp | 2 | 3 | 3 | 2 | 1 | 11 |
| jianzhichun/abaqus-mcp-server | 1 | 2 | 2 | 1 | 2 | 8 |
| knewnothing-git/ansys-mcp-server | 1 | 2 | 2 | 2 | 1 | 8 |

Fit counts the match to: stdio server, Linux host, noGUI subprocess, tool set license_check / run_script / submit_job / job_status / odb_query / model_info / viewport_png.

### MOBAI547800/abaqus-mcp-server (best fit)

Did well:
- `src/abaqus_mcp_server/abaqus_cli.py` runs every Abaqus call as an async subprocess with a timeout and kills the process on expiry. This matches our noGUI design.
- `security.py` routes every path through `validate_path` and every name through `validate_filename`. It blocks traversal and shell characters, and no tool takes a shell string.
- `log_parser.py` classifies `.sta` by the strings "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" and "THE ANALYSIS HAS BEEN TERMINATED". `job_status.py` also reads `.lck`.
- `odb_script_templates.py` generates `abaqus python` scripts that print JSON. Output is truncated before it reaches the model.
- 85 tests, including one layer that talks MCP protocol.

Could do better:
- No license check. `check_environment` runs `abaqus information=release`, which does not touch the license server. A dead DSLS server shows up as a hang until timeout.
- Runs Abaqus locally. No ssh/scp layer, no path mapping between Linux and the VM.
- No viewport tool.
- `run_script` executes any script text inside the workspace. No allow-list.
- Repo carries 100+ unrelated files (`polishing_analysis/`, `.cae`, `.inp` outputs).

### rutwikg/abaqus-mcp

Did well:
- `runner.py` runs `abaqus job=` through `subprocess.run` with a timeout and writes "[runner] TIMEOUT after Ns" into the output. `stage_deck` and `_clear_stale` remove stale `.lck`/`.sta` files before a run.
- `parsers/sta.py`, `msg.py`, `dat.py` are separate and have smoke tests with real fixtures in `tests/fixtures/validate_cube/`.
- `scripts_py27/capture_odb.py` is a worked noGUI viewport capture (see pitfalls).
- `SECURITY.md` states the threat model: a deck is code, no authentication on stdio.
- Strict separation: the server runs on system Python, kernel scripts live in `scripts_py27/` and are never imported.

Could do better:
- AGPL-3.0. Copying code makes abaqus-mcp AGPL. Read it, do not paste.
- Scope is autonomous deck repair, sweeps and CAD authoring. Most of the 3400 lines are outside our v1.
- Scripts are Python 2.7 for Abaqus 2022. They may not run on Abaqus 2026 unchanged.
- No license-server check. Timeout is the only guard.
- `tests/` has demos that need Abaqus; no mocked subprocess tests.

### TutuBarry/abaqus-mcp-pro

Did well:
- `agent.py` checks `ABAQUS_MCP_TOKEN` with `hmac.compare_digest` and rejects a missing token.
- `docs/ABAQUS_2026_VALIDATION.md` records real Abaqus 2026 runs. `tests/test_abaqus_2026_regressions.py` pins API shapes seen on 2026 (FieldValue arrays, a launcher that prints an error and exits 0).
- `tests/test_silent_failures.py` and `test_error_format.py` cover failures that look like success.
- `docs/guides/nogui.md` lists three noGUI transports: socket agent, file IPC, `nogui_server.py`.

Could do better:
- 135 tools and a Node 3D viewer. Far beyond KISS.
- Still runs an `exec()` agent inside CAE (`agent.py:584`, `gui_plugin.py:600`). The token is optional.
- Assumes Windows paths; validation was local, not over ssh.
- Stated unverified: other Abaqus versions, GUI interaction, GPU rendering.

### Cai-aa/abaqus-mcp (the popular one)

Did well:
- `mcp_server.py` is 237 lines: FastMCP, one `_send_command` helper, small tool wrappers. Easy to read.
- `tests/test_viewport_image.py` mocks the Abaqus API and isolates state with `ABAQUS_MCP_HOME`, so tests need no license.
- `get_viewport_image` returns a data URI and covers PNG, SVG, TIFF.

Could do better:
- `abaqus_mcp_plugin.py:214` runs `exec(compile(...))` on any text sent to the socket. No authentication.
- Needs a live CAE session. Our design drops that.
- Tools return strings such as `Error: ...` and no structured status.
- Only the viewport path is tested. No test for `submit_job` or ODB queries.
- `gui_error.txt` and `.claude/settings.local.json` committed.

### yezg9920-kely/abaqus-mcp

Did well:
- Fork of Cai-aa that adds `monitor_job_status` with `_tail_lines` and `_grep_tail` over `.msg`/`.sta` (`mcp_server.py:355-400`).
- `_read_message(max_bytes=MAX_MESSAGE_BYTES)` caps socket reads.
- `_format_error_to_markdown` turns a traceback into readable output.
- Default host `127.0.0.1`.

Could do better:
- Same unauthenticated `exec` bridge (`abaqus_mcp_plugin.py:297`).
- Bind host is an env var, so a user can set it to `0.0.0.0` with no warning.
- No tests.
- `inspect_odb` runs inside CAE and holds the session while it reads frames.

### jianzhichun/abaqus-mcp-server

Did well:
- First public Abaqus MCP (May 2025). Mocked unit tests for window discovery and script execution.

Could do better:
- `mcp_server.py` drives the CAE window with pywinauto and pastes script text. Breaks on any UI change, Windows only, and cannot work over ssh.
- Reads the message area by control-type heuristics (`test_get_log_success_pane_heuristic`).
- Last commit 2025-05-27.

### knewnothing-git/ansys-mcp-server (other FEA, not copied)

Did well:
- Splits tool schemas (`handle_list_tools`) from one manager class with `check_ansys_installation`.

Could do better:
- Uses the low-level `Server` API and returns plain text. `run_mapdl_commands` passes a command list to the solver. No test of the tool layer. Nothing here beats the Abaqus servers above, and the second FEA server was dropped for that reason.

## Reuse for abaqus-mcp

Copy or adapt (all MIT unless noted):

1. MOBAI `security.py` (MIT): `validate_path`, `validate_filename`, `_reject_dangerous_chars`. Adapt to remote paths: validate on the Linux side, then map to a fixed VM workspace.
2. MOBAI `log_parser.py` (MIT): `.sta` status strings and step/increment parsing. Add the `.msg` ERROR and WARNING extraction. Rutwikg `parsers/msg.py` and its `tests/fixtures/validate_cube/` give real sample files; read for ideas, do not copy (AGPL).
3. MOBAI `abaqus_cli.py` (MIT) subprocess pattern: timeout, kill on expiry, bounded output. Replace local `create_subprocess_exec` with `ssh vm "..."`. Keep the argument list, never a shell string.
4. MOBAI `odb_script_templates.py` (MIT): ODB query as a generated script that prints one JSON document. Run it with `abaqus python`, not `abaqus cae`, so no CAE license is taken.
5. Cai-aa `tests/test_viewport_image.py` (MIT): fake `abaqus` module in `sys.modules` plus a temp home. Reuse for `run_script` and `viewport_png` unit tests. Mock `ssh` the same way.
6. Rutwikg `capture_odb.py` (AGPL, concept only): the viewport recipe in the pitfalls below.

New code we still need, found in none of them:
- `license_check`: probe the DSLS port (TCP connect with a 3 to 5 s timeout) before every tool that checks out a token. Fail with a clear VPN message.
- ssh/scp transport with ControlMaster and a path map.
- A `.lck`-aware `job_status` that survives a dropped ssh session.

Pitfalls to avoid:
- Python version. Rutwikg writes kernel scripts in 2.7 for Abaqus 2022. MOBAI templates use f-strings, so they assume Python 3. Abaqus 2024 and later ship Python 3, and Tutu validated 2026, but no repo states the exact version. Check on the VM with `abaqus python -V` and write kernel scripts in Python 3 only.
- Do not import `odbAccess` in the server process. Only `abaqus python` has it (MOBAI and rutwikg both run it as a subprocess).
- ODB: open with `readOnly=True`. Close it in `finally`. Tutu's 2026 regression test shows `FieldValue` arrays do not accept every slice or invariant. Query a bounded number of frames and values. Print JSON only on stdout so Abaqus banner text cannot corrupt it.
- Job monitoring. Delete stale `.lck` and `.sta` before submit (rutwikg `_clear_stale`). Tutu records a launcher that prints an error and exits 0, so judge success from `.sta` text and `.msg`, not the exit code. Poll files over ssh with `tail`; do not hold an ssh channel for the job.
- No GUI session. Cai-aa, yezg, Tutu and jian all need a running CAE. Run `abaqus cae noGUI=script.py` per call instead.
- noGUI viewport capture (from `rutwikg/abaqus_mcp/scripts_py27/capture_odb.py`): `session.printToFile` writes nothing, silently, when the file name contains a dot (pass the base name and let `format=PNG` add the extension). Do not call `maximize()` or touch annotations under noGUI. Set `session.pngOptions.setValues(imageSize=...)` and `printOptions.setValues(vpDecorations=OFF)`. Check the file exists after the call and return an error if not. Whether noGUI rendering works on a VM without a GPU is unverified; test it before promising `viewport_png`.
- Arbitrary code. `run_script` is arbitrary code by design (Cai-aa and yezg `exec` it over an open socket). Keep it stdio only, restrict scripts to the VM workspace, and state this in the tool description.
- Windows `.bat`. MOBAI needs `cmd.exe /c call abaqus.bat`. Over ssh into the VM, test which shell the ssh server gives.
- Do not return bare strings like `Error: ...`. Return a JSON object with `status`, `error` and `hint`.
- Scope creep. Tutu has 135 tools, rutwikg auto-repairs decks. v1 stays at seven tools.
