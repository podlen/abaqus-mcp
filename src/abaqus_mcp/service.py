"""Tool logic. Transport and config are injected so tests use a fake transport."""
from __future__ import annotations

import hashlib
import json
import re
import socket
import subprocess
import time
import uuid
from pathlib import Path

from . import abaqus_scripts as scripts
from .config import Config
from .logparse import last_errors, msg_warning_groups, parse_msg, parse_sta, sta_convergence
from .security import SecurityError, truncate, validate_filename, validate_host_file, validate_name
from .transport import TransportError

UNREACHABLE = "license server unreachable"
NO_LIVE = "no live CAE session"
NO_PROJECT = "no project: call set_project"


class NoProjectError(SecurityError):
    pass


def project_key(path: Path) -> str:
    """`<slug>-<hash>` of a resolved project path: slug from the basename kept to [A-Za-z0-9_-],
    hash the first 8 hex of the sha1 of the path."""
    slug = re.sub(r"[^A-Za-z0-9_-]", "", path.name) or "project"
    return f"{slug}-{hashlib.sha1(str(path).encode()).hexdigest()[:8]}"


def psq(s: str) -> str:
    """PowerShell single-quoted literal (no expansion; only ' needs doubling)."""
    return "'" + s.replace("'", "''") + "'"


def _error(msg: str, hint: str = "") -> dict:
    return {"status": "error", "error": msg, "hint": hint}


_LICENSE_NOISE = re.compile(r"^(Successfully checked out|Abaqus License Manager|\"\w+\" from DSLS|<\d+ out of)")
_BANNER = re.compile(r'^Executing "onCaeGraphicsStartup\(\)"')
VIEWS = ("iso", "front", "back", "top", "bottom", "left", "right")
SUMMARY_KEYS = ("models", "parts", "instances", "sets", "surfaces", "materials", "sections", "assignments",
                "steps", "loads", "bcs", "interactions", "contact_props", "mesh")

# runs the user's script in a fresh namespace after the CAE modules are registered: no star import,
# so builtins such as sum stay builtins; the job dir (with abqmcp.py) is on sys.path
_WRAPPER = """import builtins, os, sys
import caeModules  # noqa: F401
sys.path.insert(0, os.getcwd())
with open({name!r}, encoding="utf-8") as _fh:
    _code = compile(_fh.read(), {name!r}, "exec")
exec(_code, {{"__name__": "__main__", "__file__": {name!r}, "__builtins__": builtins}})
"""
HELPER = Path(__file__).parent / "kernel" / "abqmcp.py"


def compact(text: str, cap: int) -> str:
    """Runs of identical lines (after rstrip) as one line plus ` [xN]`, then the last `cap` characters."""
    out, prev, n = [], None, 0
    for line in text.splitlines() + [None]:
        line = line.rstrip() if line is not None else None
        if line == prev:
            n += 1
            continue
        if prev is not None:
            out.append(prev + (f" [x{n}]" if n > 1 else ""))
        prev, n = line, 1
    text = "\n".join(out)
    if cap and len(text) > cap:
        return f"[... {len(text) - cap} chars cut]\n" + text[-cap:]
    return text
_EXC = re.compile(r"^\w*(Error|Exception|Exit)\b.*")


def _traceback(stderr: str, rpy: str = "") -> str:
    """Exception text of a failed `cae noGUI` run: stderr minus license chatter (Abaqus prints no
    'Traceback' header), else the `#* ` lines of abaqus.rpy."""
    lines = [l for l in stderr.splitlines() if l.strip() and not _LICENSE_NOISE.match(l.strip())]
    if not lines:
        lines = [l[3:] for l in rpy.splitlines() if l.startswith("#* ")]
    return "\n".join(lines).strip()


def _first_exc(tb: str) -> str:
    return next((l for l in tb.splitlines() if _EXC.match(l)), tb.splitlines()[0] if tb else "")


def _failed(r) -> bool:
    return r.returncode != 0 or r.timed_out or "Abaqus Error:" in r.stdout or "Abaqus Error:" in r.stderr


def _json_from(text: str) -> dict | None:
    a, b = text.find(scripts.START), text.find(scripts.END)
    if a < 0 or b < a:
        return None
    try:
        return json.loads(text[a + len(scripts.START):b])
    except json.JSONDecodeError:
        return None


class Service:
    def __init__(self, cfg: Config, transport) -> None:
        self.cfg = cfg
        self.t = transport
        self.project: Path | None = None

    # -- paths -------------------------------------------------------------
    def set_project(self, path: str) -> dict:
        """Sets the analysis directory of this session; a second call switches projects. Jobs read
        and write <path>/<job>/, input files at <path>/ are found by name, and the VM mirror is
        C:\\abaqus-work\\<name>-<hash>\\<job>. path must be under the home directory; a new
        directory is created."""
        try:
            p = Path(path).expanduser().resolve()
            if not p.is_relative_to(Path.home().resolve()):
                raise SecurityError(f"project path {path!r} is not under the home directory")
            p.mkdir(parents=True, exist_ok=True)
        except (SecurityError, OSError) as e:
            return _error(str(e))
        self.project = p
        return {"status": "ok", "project": str(p), "vm_dir": self.vm_root}

    def _need_project(self) -> Path:
        if self.project is None:
            raise NoProjectError(NO_PROJECT)
        return self.project

    @property
    def vm_root(self) -> str:
        return f"{self.cfg.work_vm}\\{project_key(self._need_project())}"

    def _in_project(self, path: str) -> Path:
        """Host input file: a bare name is looked up in the project directory."""
        if "/" in path or "\\" in path or path.startswith("~"):
            return validate_host_file(path)
        return validate_host_file(self._need_project() / path)

    def _vm(self, job: str) -> str:
        return f"{self.vm_root}\\{validate_name(job)}"

    def _host(self, job: str) -> Path:
        d = self._need_project() / validate_name(job)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _prep(self, job: str) -> str:
        d = self._vm(job)
        self._host(job)
        r = self.t.run(f"New-Item -ItemType Directory -Force -Path {psq(d)} | Out-Null", self.cfg.ssh_timeout)
        if r.returncode != 0:
            raise TransportError(f"cannot create {d} on the VM: {r.stderr.strip() or r.stdout.strip()}")
        return d

    def _abq(self, vmdir: str, args: str, timeout: float):
        a = self.cfg.abaqus_cmd
        cmd = (f"$ErrorActionPreference='Stop'; Set-Location -LiteralPath {psq(vmdir)}; "
               f"if (-not (Test-Path -LiteralPath {psq(a)})) "
               f"{{ [Console]::Error.WriteLine({psq('abaqus not found on the VM: ' + a)}); exit 127 }}; "
               f"$ErrorActionPreference='Continue'; & {psq(a)} {args}; exit $LASTEXITCODE")
        return self.t.run(cmd, timeout)

    def _fetch_json(self, job: str, d: str, name: str) -> dict | None:
        """Fetch the JSON file an Abaqus-side script wrote into the job dir."""
        local = self._host(job) / name
        local.unlink(missing_ok=True)
        try:
            self.t.get(f"{d}\\{name}", local)
            return json.loads(local.read_text())
        except (TransportError, OSError, ValueError):
            return None

    def _upload(self, job: str, host_file: Path, name: str | None = None) -> str:
        d = self._vm(job)
        name = name or host_file.name
        self.t.put(host_file, f"{d}\\{validate_filename(name)}")
        return name

    def _cae(self, job: str, cae_file: str) -> str:
        """A path (contains a separator or starts with ~) is uploaded from the host. A bare name
        is uploaded from the project directory when it is there, else it is a file already in the
        VM job dir; it is never looked up in the server's cwd."""
        if "/" in cae_file or "\\" in cae_file or cae_file.startswith("~"):
            return self._upload(job, validate_host_file(cae_file))
        if (self._need_project() / validate_filename(cae_file)).is_file():
            return self._upload(job, self._need_project() / cae_file)
        return cae_file

    def _upload_text(self, job: str, text: str, name: str) -> str:
        p = self._host(job) / name
        p.write_text(text)
        return self._upload(job, p)

    # -- license -----------------------------------------------------------
    def _probe(self, timeout: float) -> bool:
        try:
            with socket.create_connection((self.cfg.license_host, self.cfg.license_port), timeout=timeout):
                return True
        except OSError:
            return False

    def license_check(self) -> dict:
        """TCP probe of the licence server; on failure run `abaqus-vpn up` once (when configured) and
        probe again (about 23 s worst case). Without a known licence host the probe is skipped."""
        t0 = time.monotonic()
        if not self.cfg.license_host:
            return {"status": "ok", "license": "not checked", "vpn_started": False,
                    "hint": "no license_host in config.local.toml and none in DSLicSrv.txt"}
        if self._probe(self.cfg.probe_timeout):
            return {"status": "ok", "license": "reachable", "vpn_started": False}
        if not self.cfg.vpn_cmd:
            return {"status": "error", "error": UNREACHABLE,
                    "hint": f"{self.cfg.license_host}:{self.cfg.license_port} closed; connect the university VPN",
                    "elapsed_s": round(time.monotonic() - t0, 1)}
        try:
            subprocess.run([self.cfg.vpn_cmd, "up"], capture_output=True, timeout=self.cfg.vpn_timeout)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if self._probe(self.cfg.probe_timeout):
            return {"status": "ok", "license": "reachable", "vpn_started": True}
        return {"status": "error", "error": UNREACHABLE,
                "hint": f"{self.cfg.license_host}:{self.cfg.license_port} closed after abaqus-vpn up; "
                        "check `bin/abaqus-vpn status`", "elapsed_s": round(time.monotonic() - t0, 1)}

    def _guard(self) -> dict | None:
        r = self.license_check()
        return None if r["status"] == "ok" else r


    # -- live CAE session (C2) ---------------------------------------------
    @property
    def _live(self) -> str:
        return self.cfg.work_vm + "\\live"

    def _live_age(self) -> float | None:
        """Heartbeat age in seconds on the VM clock (no host/VM clock skew), None when missing or stale."""
        hb = psq(self._live + "\\heartbeat.txt")
        # "$(...)" formats with the invariant culture; a bare double prints 0,53 under sl-SI
        cmd = (f"$p={hb}; if (Test-Path -LiteralPath $p) {{ try {{ $t=[double](Get-Content -LiteralPath $p -Raw); "
               "\"$([math]::Round([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000 - $t, 2))\" } catch { } }; exit 0")
        try:
            r = self.t.run(cmd, self.cfg.live_probe_timeout)
        except TransportError:
            return None
        if r.timed_out or r.returncode != 0:
            return None
        try:
            age = float(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None
        return age if age <= self.cfg.live_stale_s else None

    def cae_live(self, script: str, timeout: int = 60) -> dict:
        """Runs Python in the open Abaqus/CAE GUI session (its kernel: `mdb`, `session` and the
        abaqus modules are in scope), so edits appear in the open model tree. Needs the live-bridge plug-in
        and a CAE window; otherwise returns "no live CAE session" within 5 s. The script waits until no
        GUI dialog or procedure is active. Output (print) and a variable named `result` (JSON-able)
        come back; an exception comes back as `traceback`. `import abqmcp` works as in run_script. Every script is kept in
        C:\\abaqus-work\\live\\log on the VM."""
        t0 = time.monotonic()
        if self._live_age() is None:
            hint = ("start Abaqus/CAE (`abaqus cae`); the plug-in is installed by setup-windows.cmd"
                    if self.cfg.transport == "local" else
                    "start CAE with bin/abaqus-gui (plug-in installed by vm/install-live-plugin.sh)")
            return _error(NO_LIVE, hint)
        sid = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
        local = self.cfg.state_dir / "_live" / f"{sid}.part"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(script, encoding="utf-8")
        live, timeout = self._live, max(1, int(timeout))
        part, py = f"{live}\\inbox\\{sid}.part", f"{live}\\inbox\\{sid}.py"
        out = f"{live}\\outbox\\{sid}.json"
        try:
            self._live_helper()
            self.t.put(local, part)
            # one SSH call: publish the script, poll the outbox every 0.25 s on the VM, print the result
            cmd = (f"Move-Item -LiteralPath {psq(part)} -Destination {psq(py)}; $o={psq(out)}; "
                   f"$end=(Get-Date).AddSeconds({timeout}); "
                   "while (-not (Test-Path -LiteralPath $o)) { if ((Get-Date) -gt $end) { "
                   f"try {{ Remove-Item -LiteralPath {psq(py)} -ErrorAction Stop; 'MCP_LIVE_NOTRUN' }} catch {{ 'MCP_LIVE_TIMEOUT' }}; exit 0 }}; "
                   "Start-Sleep -Milliseconds 250 }; Get-Content -LiteralPath $o -Raw -Encoding UTF8; "
                   f"Remove-Item -LiteralPath $o -ErrorAction SilentlyContinue; exit 0")
            r = self.t.run(cmd, timeout + self.cfg.ssh_timeout)
        except TransportError as e:
            return _error(str(e))
        finally:
            local.unlink(missing_ok=True)
        text = r.stdout.strip()
        if text.endswith("MCP_LIVE_NOTRUN"):
            return _error("timed out, not run", f"the script was still in the inbox after {timeout} s and was deleted; id {sid}")
        if r.timed_out or text.endswith("MCP_LIVE_TIMEOUT"):
            return _error("timed out while running",
                          f"no result within {timeout} s; the script was picked up and may still run; log id {sid} (C:\\abaqus-work\\live\\log\\{sid}.py on the VM)")
        try:
            d = json.loads(text)
        except ValueError:
            return _error("unreadable result from the live bridge", truncate(text + r.stderr, 2000))
        out_d = {"status": "ok" if d.get("ok") else "error", "id": sid, "output": d.get("output", ""),
                 "result": d.get("result"), "traceback": d.get("traceback", ""),
                 "elapsed_s": round(time.monotonic() - t0, 2)}
        if not d.get("ok"):
            out_d["error"] = _first_exc(d.get("traceback", "")) or "script failed"
        return out_d

    def _live_helper(self) -> None:
        """abqmcp.py into the live dir (on the kernel path through mcp_live_kernel), once per server."""
        if not getattr(self, "_helper_put", False):
            self.t.put(HELPER, f"{self._live}\\abqmcp.py")
            self._helper_put = True

    def _live_session(self) -> bool:
        return self._live_age() is not None

    # -- tools -------------------------------------------------------------
    def run_script(self, job: str, script_path: str, inputs: list[str] | None = None,
                   outputs: list[str] | None = None, timeout: int | None = None) -> dict:
        """Runs a Python script in Abaqus/CAE (`abaqus cae noGUI`) in the job dir. The CAE modules are
        loaded first (mdb.openStep, part and mesh methods exist; no star import, so import what you
        use: `from abaqus import mdb`, `from abaqusConstants import *`). `import abqmcp` gives the
        partition and mesh helpers (import_solid, prism, tool_box, tool_cylinder, imprint, cut,
        mesh_plan, seed_bias, mesh_report).
        inputs: host files (bare names from the project dir, or paths) uploaded to the job dir first.
        outputs: file names copied from the job dir to <project>/<job>/ afterwards, listed in
        `fetched` and `missing`. print() comes back as `print_output`, sys.__stdout__ as `stdout`,
        each with repeated lines collapsed (`line [xN]`) and only the last print_cap (4000) characters.
        On failure also `stderr` and `traceback` (line numbers of your script). A run is an error on
        `Abaqus Error:` or a non-zero exit."""
        try:
            self._need_project()
            for n in outputs or []:
                validate_filename(n)
            if (g := self._guard()):
                return g
            src = self._in_project(script_path)
            ins = [self._in_project(p) for p in inputs or []]
            d = self._prep(job)
            name = self._upload(job, src)
            for p in ins:
                self._upload(job, p)
            self.t.put(HELPER, f"{d}\\abqmcp.py")
            self._upload_text(job, _WRAPPER.format(name=name), "_mcp_run.py")
            # fresh abaqus.rpy: only this run's lines are read back
            self.t.run(f"Remove-Item -LiteralPath {psq(d + chr(92) + 'abaqus.rpy')} -ErrorAction SilentlyContinue; exit 0",
                       self.cfg.ssh_timeout)
            r = self._abq(d, "cae noGUI=_mcp_run.py", timeout or self.cfg.script_timeout)
            rpy = self.t.run(f"Get-Content -LiteralPath {psq(d + chr(92) + 'abaqus.rpy')} "
                             "-ErrorAction SilentlyContinue; exit 0", self.cfg.ssh_timeout).stdout
            fetched, missing = [], []
            for n in outputs or []:
                local = self._host(job) / n
                local.unlink(missing_ok=True)
                try:
                    self.t.get(f"{d}\\{n}", local)
                    fetched.append(str(local))
                except (TransportError, OSError):
                    missing.append(n)
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        cap = self.cfg.print_cap
        printed = "\n".join(l[3:] for l in rpy.splitlines() if l.startswith("#: ") and not _BANNER.match(l[3:]))
        failed = _failed(r)
        out = {"status": "error" if failed else "ok", "exit_code": r.returncode, "timed_out": r.timed_out,
               "print_output": compact(printed, cap), "stdout": compact(r.stdout, cap)}
        if outputs:
            out.update(fetched=fetched, missing=missing)
        if failed:
            tb = _traceback(r.stderr, rpy)
            err = "\n".join(l for l in r.stderr.splitlines() if not _LICENSE_NOISE.match(l.strip()))
            out.update(stderr=compact(err, cap), traceback=tb,
                       error="timeout" if r.timed_out else (_first_exc(tb) or "script failed"))
        out["elapsed_s"] = round(r.elapsed, 1)
        return out

    def submit_job(self, job: str, inp_file: str | None = None, cae_file: str | None = None,
                   model: str = "Model-1", cpus: int = 1, background: bool = False,
                   timeout: int | None = None) -> dict:
        """Submit from a host .inp, or from a .cae: cae_file is a host path (with a directory part, or ~)
        that is uploaded, or a bare name found in the project directory (else already in the VM job dir)."""
        try:
            self._need_project()
            if bool(inp_file) == bool(cae_file):
                return _error("give exactly one of inp_file or cae_file")
            if (g := self._guard()):
                return g
            validate_name(model)
            d = self._prep(job)
            if inp_file:
                inp = self._upload(job, self._in_project(inp_file), f"{job}.inp")
            else:
                cae = self._cae(job, cae_file)
                self._upload_text(job, scripts.write_inp(cae, model, job), "_write_inp.py")
                w = self._abq(d, "cae noGUI=_write_inp.py", self.cfg.script_timeout)
                if _failed(w) or not _json_from(w.stdout):
                    return _error("writing the input file from the .cae failed",
                                  _traceback(w.stderr) or truncate(w.stderr, 2000))
                inp = f"{job}.inp"
            # stale files from an earlier run would fake a status (prior-art: rutwikg _clear_stale)
            stale = ",".join(psq(f"{job}{e}") for e in (".lck", ".sta", ".msg", ".dat", ".odb"))
            self.t.run(f"Set-Location -LiteralPath {psq(d)}; Remove-Item -ErrorAction SilentlyContinue "
                       f"{stale}; exit 0", self.cfg.ssh_timeout)
            cmd = f"job={job} input={inp} cpus={int(cpus)} interactive"
            if background:
                # Win32_Process.Create: the child is not tied to the SSH session (Start-Process
                # children die when it closes, see docs/decisions.md)
                line = f'cmd.exe /c ""{self.cfg.abaqus_cmd}" {cmd} > "{job}.log" 2>&1"'
                ps = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
                      f"@{{CommandLine={psq(line)}; CurrentDirectory={psq(d)}}}; "
                      "if ($r.ReturnValue -ne 0) { [Console]::Error.WriteLine('Create failed: ' + $r.ReturnValue); exit 1 }; "
                      "$r.ProcessId")
                r = self.t.run(ps, self.cfg.ssh_timeout)
                return {"status": "started" if r.returncode == 0 else "error", "job": job,
                        "hint": "poll with job_status", "stderr": r.stderr}
            r = self._abq(d, cmd, timeout or self.cfg.job_timeout)
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        st = self.job_status(job)
        st["exit_code"] = r.returncode
        st["timed_out"] = r.timed_out
        if r.returncode != 0 and st.get("status") not in ("failed", "aborted"):
            st["stderr"] = r.stderr
        return st

    def job_status(self, job: str) -> dict:
        """Status from .sta, .msg, .lck (and ***ERROR lines of .dat when no .sta/.msg exist), with per-step
        convergence detail and grouped warnings. The exit code is not trusted (prior-art)."""
        try:
            d = self._vm(job)
            def part(tag, f):
                return f"'==={tag}==='; if (Test-Path {psq(f)}) {{ Get-Content {psq(f)} }}; "
            cmd = (f"Set-Location -LiteralPath {psq(d)}; " + part("STA", f"{job}.sta") + part("MSG", f"{job}.msg")
                   + f"'===DAT==='; if (Test-Path {psq(job + '.dat')}) {{ Get-Content {psq(job + '.dat')} | "
                   "Select-String -Pattern '\\*\\*\\*ERROR' -Context 0,3 | ForEach-Object { $_.Line; $_.Context.PostContext } }; "
                   + f"'===LCK==='; if (Test-Path {psq(job + '.lck')}) {{ 'yes' }}; '===END==='")
            r = self.t.run(cmd, self.cfg.ssh_timeout)
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        if r.returncode != 0 and "===STA===" not in r.stdout:
            return _error("cannot read job directory", r.stderr.strip())
        parts = {}
        cur = None
        for line in r.stdout.splitlines():
            if line.strip() in ("===STA===", "===MSG===", "===DAT===", "===LCK===", "===END==="):
                cur = line.strip().strip("=")
                parts[cur] = []
            elif cur:
                parts[cur].append(line)
        sta_t, msg_t = "\n".join(parts.get("STA", [])), "\n".join(parts.get("MSG", []))
        locked = "yes" in parts.get("LCK", [])
        dat_t = "\n".join(parts.get("DAT", []))
        sta, msg = parse_sta(sta_t), parse_msg(msg_t)
        dat_err = parse_msg(dat_t)["errors"] if not sta_t.strip() and not msg_t.strip() else []
        status = sta["status"]
        if status != "completed":
            if msg["n_errors"] or dat_err:
                status = "failed"
            elif locked:
                status = "running"
            elif not sta_t.strip() and not msg_t.strip():
                status = "not_found"
        out = {"status": status, "job": job, "locked": locked,
               "errors": last_errors(msg_t) if msg["n_errors"] else dat_err[-5:],
               "warnings": msg["warnings"][:3], "n_warnings": msg["n_warnings"]}
        out.update({k: v for k, v in sta.items() if k != "status"})
        if sta_t.strip():
            out["steps"] = sta_convergence(sta_t)
        if msg["n_warnings"]:
            out["warning_groups"] = msg_warning_groups(msg_t)
        return out

    def _python_json(self, job: str, script: str, name: str, cae: bool = False) -> dict:
        """Run a script that writes <name>.json (P["result"]) into the job dir; fetch and parse it."""
        d = self._vm(job)
        out = name.replace(".py", ".json")
        self._upload_text(job, script, name)
        self.t.run(f"Remove-Item -LiteralPath {psq(d + chr(92) + out)} -ErrorAction SilentlyContinue; exit 0",
                   self.cfg.ssh_timeout)
        # odbAccess needs only `abaqus python` (no CAE token); mdb needs the CAE kernel
        r = self._abq(d, f"cae noGUI={name}" if cae else f"python {name}", self.cfg.script_timeout)
        data = self._fetch_json(job, d, out)
        if data is None:
            return _error("no JSON file from Abaqus", _traceback(r.stderr) or truncate(r.stderr, 2000))
        return data if "error" not in data else {"status": "error", **data}

    def odb_query(self, job: str, step: str, frame: int = -1, variable: str | None = "U",
                  set_name: str | None = None, component: str | None = None, max_values: int = 1000) -> dict:
        """Field output of <job>.odb at step/frame, optionally for a node/element set, as JSON.
        Also lists up to 50 frames with their frequency (frequency steps)."""
        try:
            for n in (step, set_name, component, variable):
                if n:
                    validate_name(n)
            self._prep(job)
            s = scripts.odb_query(f"{job}.odb", step, frame, variable, set_name, component, max_values, "_odb_query.json")
            res = self._python_json(job, s, "_odb_query.py")
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        res.setdefault("status", "ok")
        return res

    def odb_history(self, job: str, step: str | None = None, region: str | None = None,
                    outputs: list[str] | None = None) -> dict:
        """History output of <job>.odb. Without outputs: regions and their output names per step. With
        outputs (e.g. ["RF2", "ALLIE"]): [time, value] series, at most 200 points each, first, last,
        min and max kept; region is a case-insensitive part of the region name."""
        try:
            if step:
                validate_name(step)
            if region and not re.fullmatch(r"[A-Za-z0-9_. -]{1,100}", region):
                raise SecurityError(f"invalid region {region!r}")
            for o in outputs or []:
                validate_name(o)
            self._prep(job)
            s = scripts.odb_history(f"{job}.odb", step, region, outputs or None, 200, "_odb_history.json")
            res = self._python_json(job, s, "_odb_history.py")
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        res.setdefault("status", "ok")
        return res

    def model_summary(self, job: str, cae_file: str | None = None, model: str | None = None,
                      live: bool = True, only: list[str] | None = None) -> dict:
        """JSON summary of a .cae (schema: docs/model_summary.schema.json): parts, instances, sets,
        surfaces, materials, sections, steps, loads, BCs, interactions, mesh; under 20 kB, long lists
        cut with `omitted` counts. cae_file is a host path (with a directory part, or ~) that is
        uploaded, or a bare name already in the VM job dir. Default <job>.cae; model default is the
        first model. Without cae_file, and when a live CAE session answers (live=True), the open
        session is summarised (unsaved edits included, source "live"). only: top-level keys to return
        (e.g. ["mesh"]; also source, model, omitted, status). mesh.techniques counts cells per part by
        assigned shape and technique; mesh.warning appears above config node_limit."""
        try:
            if model:
                validate_name(model)
            bad = [k for k in only or [] if k not in SUMMARY_KEYS]
            if bad:
                return _error(f"unknown summary keys {bad}", "one of " + ", ".join(SUMMARY_KEYS))
            self._need_project()
            if live and not cae_file and self._live_session():
                res = self._live_json(scripts.live_summary(model))
                if res.get("status") != "error" or res.get("error") != NO_LIVE:
                    return self._trim_summary(res, only)
            if (g := self._guard()):
                return g
            self._prep(job)
            cae = self._cae(job, cae_file) if cae_file else f"{job}.cae"
            s = scripts.model_summary(cae, model, cae, "_model_summary.json")
            res = self._python_json(job, s, "_model_summary.py", cae=True)
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        res.setdefault("status", "ok")
        return self._trim_summary(res, only)

    def _trim_summary(self, res: dict, only: list[str] | None) -> dict:
        mesh = res.get("mesh")
        if isinstance(mesh, dict) and self.cfg.node_limit and mesh.get("nodes", 0) > self.cfg.node_limit:
            mesh["warning"] = f"{mesh['nodes']} nodes > node_limit {self.cfg.node_limit}"
        if only and res.get("status") != "error":
            res = {k: v for k, v in res.items() if k in (*only, "source", "model", "omitted", "status")}
        return res

    def _view_args(self, highlight, views, size):
        hl = highlight if isinstance(highlight, list) else [highlight] if highlight else []
        for n in hl:
            validate_name(n)
        views = list(views) if views else (["iso"] if isinstance(highlight, list) else ["iso", "front", "top"])
        if not views or any(v not in VIEWS for v in views):
            raise SecurityError(f"views must be from {VIEWS}")
        w, h = (int(x) for x in size)
        if not (100 <= w <= 4000 and 100 <= h <= 4000):
            raise SecurityError("size must be [width, height], 100 to 4000 px")
        return views, (w, h)

    @staticmethod
    def _view_files(job, highlight, views):
        """(key in paths, file stem) per PNG; a list of highlights is keyed "<name>:<view>"."""
        if isinstance(highlight, list):
            return [(f"{h}:{v}", f"{job}_views_{h}_{v}") for h in highlight for v in views]
        base = f"{job}_views" + (f"_{highlight}" if highlight else "")
        return [(v, f"{base}_{v}") for v in views]

    def model_views(self, job: str, cae_file: str | None = None, model: str | None = None,
                    highlight: str | list[str] | None = None, views: list[str] | None = None,
                    size: list[int] = (900, 600), live: bool = True) -> dict:
        """PNGs of the assembly (the first part when there are no instances) of a .cae, copied to
        <project>/<job>/. highlight: one set or surface name, drawn red, or a list of them (one PNG per
        name and view, keyed "<name>:<view>", all from one CAE run). views: from iso, front, back, top,
        bottom, left, right; default iso, front, top, or iso only for a list. size: [width, height] px.
        cae_file and model as in model_summary. Without cae_file, and with a live CAE session, the open
        model is drawn in a viewport of that session (its displayed object is restored afterwards)."""
        try:
            self._need_project()
            if model:
                validate_name(model)
            views, size = self._view_args(highlight, views, size)
            files = self._view_files(job, highlight, views)
            if live and not cae_file and self._live_session():
                res = self._live_views(job, model, highlight, views, size, files)
                if res.get("status") != "error" or res.get("error") != NO_LIVE:
                    return res
            if (g := self._guard()):
                return g
            d = self._prep(job)
            cae = self._cae(job, cae_file) if cae_file else f"{job}.cae"
            # no dot in the name: printToFile writes nothing otherwise
            base = f"{job}_views" + (f"_{highlight}" if isinstance(highlight, str) else "")
            self._upload_text(job, scripts.model_views(cae, base, model, highlight, views, size), "_model_views.py")
            r = self._abq(d, "cae noGUI=_model_views.py", self.cfg.script_timeout)
            data = _json_from(r.stdout)
            if not data or not data.get("ok"):
                return _error("view PNGs not written", _traceback(r.stderr) or truncate(r.stderr, 2000))
            paths = {}
            for key, stem in files:
                local = self._host(job) / f"{stem}.png"
                self.t.get(f"{d}\\{stem}.png", local)
                paths[key] = str(local)
        except (SecurityError, TransportError, ValueError, TypeError) as e:
            return _error(str(e))
        return {"status": "ok", "paths": paths, "shown": data.get("shown"), "highlight": highlight}

    def viewport_png(self, job: str, step_index: int = 0, frame: int = -1, variable: str = "U",
                     invariant: str | None = None) -> dict:
        """Render <job>.odb with noGUI printToFile; the PNG lands in <project>/<job>/."""
        try:
            self._need_project()
            validate_name(variable)
            if invariant:
                validate_name(invariant)
            if (g := self._guard()):
                return g
            d = self._prep(job)
            base = f"{job}_view"  # no dot in the name: printToFile writes nothing otherwise
            s = scripts.viewport(f"{job}.odb", base, int(step_index), int(frame), variable, invariant)
            self._upload_text(job, s, "_viewport.py")
            r = self._abq(d, "cae noGUI=_viewport.py", self.cfg.script_timeout)
            data = _json_from(r.stdout)
            if not data or not data.get("ok"):
                return _error("viewport PNG not written", _traceback(r.stderr) or truncate(r.stderr, 2000))
            local = self._host(job) / f"{base}.png"
            self.t.get(f"{d}\\{base}.png", local)
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        return {"status": "ok", "path": str(local)}

    def _live_json(self, script: str, timeout: int = 120) -> dict:
        r = self.cae_live(script, timeout)
        if r["status"] != "ok":
            return r
        res = r.get("result")
        if not isinstance(res, dict):
            return _error("live script returned no result", truncate(r.get("output", ""), 2000))
        res.setdefault("status", "ok")
        return res

    def _live_views(self, job: str, model, highlight, views, size, files) -> dict:
        base = f"{self._live}\\views\\{job}_views" + (f"_{highlight}" if isinstance(highlight, str) else "")
        res = self._live_json(scripts.live_views(base, model, highlight, views, size))
        if res.get("status") == "error" or not res.get("files"):
            return res if res.get("status") == "error" else _error("view PNGs not written")
        paths = {}
        try:
            for key, stem in files:
                local = self._host(job) / f"{stem}.png"
                self.t.get(f"{self._live}\\views\\{stem}.png", local)
                paths[key] = str(local)
        except TransportError as e:
            return _error(str(e))
        return {"status": "ok", "paths": paths, "shown": res.get("shown"), "highlight": highlight, "source": "live"}
