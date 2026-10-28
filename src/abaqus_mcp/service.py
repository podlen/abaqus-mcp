"""Tool logic. Transport and config are injected so tests use a fake transport."""
from __future__ import annotations

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


def psq(s: str) -> str:
    """PowerShell single-quoted literal (no expansion; only ' needs doubling)."""
    return "'" + s.replace("'", "''") + "'"


def _error(msg: str, hint: str = "") -> dict:
    return {"status": "error", "error": msg, "hint": hint}


_LICENSE_NOISE = re.compile(r"^(Successfully checked out|Abaqus License Manager|\"\w+\" from DSLS|<\d+ out of)")
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

    # -- paths -------------------------------------------------------------
    def _vm(self, job: str) -> str:
        return f"{self.cfg.work_vm}\\{validate_name(job)}"

    def _host(self, job: str) -> Path:
        d = self.cfg.work_host / validate_name(job)
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
        is a file already in the VM job dir; it is never looked up in the server's cwd."""
        if "/" in cae_file or "\\" in cae_file or cae_file.startswith("~"):
            return self._upload(job, validate_host_file(cae_file))
        return validate_filename(cae_file)

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
        """TCP probe; on failure run `abaqus-vpn up` once and probe again (about 23 s worst case)."""
        t0 = time.monotonic()
        if self._probe(self.cfg.probe_timeout):
            return {"status": "ok", "license": "reachable", "vpn_started": False}
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
        cmd = (f"$p={hb}; if (Test-Path -LiteralPath $p) {{ try {{ $t=[double](Get-Content -LiteralPath $p -Raw); "
               "[math]::Round([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000 - $t, 2) } catch { } }; exit 0")
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
        come back; an exception comes back as `traceback`. Every script is kept in
        C:\\abaqus-work\\live\\log on the VM."""
        t0 = time.monotonic()
        if self._live_age() is None:
            return _error(NO_LIVE, "start CAE with bin/abaqus-gui (plug-in installed by vm/install-live-plugin.sh)")
        sid = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
        local = self.cfg.work_host / "_live" / f"{sid}.part"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(script, encoding="utf-8")
        live, timeout = self._live, max(1, int(timeout))
        part, py = f"{live}\\inbox\\{sid}.part", f"{live}\\inbox\\{sid}.py"
        out = f"{live}\\outbox\\{sid}.json"
        try:
            self.t.put(local, part)
            # one ssh call: publish the script, poll the outbox every 0.25 s on the VM, print the result
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

    def _live_session(self) -> bool:
        return self._live_age() is not None

    # -- tools -------------------------------------------------------------
    def run_script(self, job: str, script_path: str, timeout: int | None = None) -> dict:
        """Executes arbitrary Python in Abaqus/CAE on the VM: uploads a .py to the job dir and runs
        `abaqus cae noGUI=<script>`.
        print() and sys.stderr output of the script is not on stdout: it is returned as `print_output`,
        read from the `#: ` lines this run wrote to abaqus.rpy. Write results to a file or sys.__stdout__
        to get them in `stdout`. A run is an error on `Abaqus Error:` in stdout/stderr or a non-zero exit."""
        try:
            if (g := self._guard()):
                return g
            src = validate_host_file(script_path)
            d = self._prep(job)
            name = self._upload(job, src)
            # fresh abaqus.rpy: only this run's lines are read back
            self.t.run(f"Remove-Item -LiteralPath {psq(d + chr(92) + 'abaqus.rpy')} -ErrorAction SilentlyContinue; exit 0",
                       self.cfg.ssh_timeout)
            r = self._abq(d, f"cae noGUI={name}", timeout or self.cfg.script_timeout)
            rpy = self.t.run(f"Get-Content -LiteralPath {psq(d + chr(92) + 'abaqus.rpy')} "
                             "-ErrorAction SilentlyContinue; exit 0", self.cfg.ssh_timeout).stdout
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        printed = "\n".join(l[3:] for l in rpy.splitlines() if l.startswith("#: "))
        failed = _failed(r)
        tb = _traceback(r.stderr, rpy) if failed else ""
        out = {"status": "error" if failed else "ok", "exit_code": r.returncode, "timed_out": r.timed_out,
               "print_output": printed, "stdout": r.stdout, "stderr": r.stderr, "traceback": tb,
               "elapsed_s": round(r.elapsed, 1)}
        if failed:
            out["error"] = "timeout" if r.timed_out else (_first_exc(tb) or "script failed")
        return out

    def submit_job(self, job: str, inp_file: str | None = None, cae_file: str | None = None,
                   model: str = "Model-1", cpus: int = 1, background: bool = False,
                   timeout: int | None = None) -> dict:
        """Submit from a host .inp, or from a .cae: cae_file is a host path (with a directory part, or ~)
        that is uploaded, or a bare file name already in the VM job dir."""
        try:
            if bool(inp_file) == bool(cae_file):
                return _error("give exactly one of inp_file or cae_file")
            if (g := self._guard()):
                return g
            validate_name(model)
            d = self._prep(job)
            if inp_file:
                inp = self._upload(job, validate_host_file(inp_file), f"{job}.inp")
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
                # Win32_Process.Create: the child is not tied to the ssh session (Start-Process
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
                      live: bool = True) -> dict:
        """JSON summary of a .cae (schema: docs/model_summary.schema.json): parts, instances, sets,
        surfaces, materials, sections, steps, loads, BCs, interactions, mesh; under 20 kB, long lists
        cut with `omitted` counts. cae_file is a host path (with a directory part, or ~) that is
        uploaded, or a bare name already in the VM job dir. Default <job>.cae; model default is the
        first model. Without cae_file, and when a live CAE session answers (live=True), the open
        session is summarised (unsaved edits included, source "live")."""
        try:
            if model:
                validate_name(model)
            if live and not cae_file and self._live_session():
                res = self._live_json(scripts.live_summary(model))
                if res.get("status") != "error" or res.get("error") != NO_LIVE:
                    return res
            if (g := self._guard()):
                return g
            self._prep(job)
            cae = self._cae(job, cae_file) if cae_file else f"{job}.cae"
            s = scripts.model_summary(cae, model, cae, "_model_summary.json")
            res = self._python_json(job, s, "_model_summary.py", cae=True)
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        res.setdefault("status", "ok")
        return res

    def model_views(self, job: str, cae_file: str | None = None, model: str | None = None,
                    highlight: str | None = None, live: bool = True) -> dict:
        """Iso, front and top PNGs of the assembly (the first part when there are no instances) of a
        .cae, optionally with one set or surface highlighted; copied to <work_host>/<job>/. cae_file
        and model as in model_summary. Without cae_file, and with a live CAE session, the open model is
        drawn in a viewport of that session (its displayed object is restored afterwards)."""
        try:
            for n in (model, highlight):
                if n:
                    validate_name(n)
            if live and not cae_file and self._live_session():
                res = self._live_views(job, model, highlight)
                if res.get("status") != "error" or res.get("error") != NO_LIVE:
                    return res
            if (g := self._guard()):
                return g
            d = self._prep(job)
            cae = self._cae(job, cae_file) if cae_file else f"{job}.cae"
            # no dot in the name: printToFile writes nothing otherwise
            base = f"{job}_views" + (f"_{highlight}" if highlight else "")
            self._upload_text(job, scripts.model_views(cae, base, model, highlight), "_model_views.py")
            r = self._abq(d, "cae noGUI=_model_views.py", self.cfg.script_timeout)
            data = _json_from(r.stdout)
            if not data or not data.get("ok"):
                return _error("view PNGs not written", _traceback(r.stderr) or truncate(r.stderr, 2000))
            paths = {}
            for v in ("iso", "front", "top"):
                local = self._host(job) / f"{base}_{v}.png"
                self.t.get(f"{d}\\{base}_{v}.png", local)
                paths[v] = str(local)
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        return {"status": "ok", "paths": paths, "shown": data.get("shown"), "highlight": highlight}

    def viewport_png(self, job: str, step_index: int = 0, frame: int = -1, variable: str = "U",
                     invariant: str | None = None) -> dict:
        """Render <job>.odb with noGUI printToFile; the PNG lands in ~/abaqus-work/<job>/."""
        try:
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

    def _live_views(self, job: str, model, highlight) -> dict:
        base = f"{self._live}\\views\\{job}_views" + (f"_{highlight}" if highlight else "")
        res = self._live_json(scripts.live_views(base, model, highlight))
        if res.get("status") == "error" or not res.get("files"):
            return res if res.get("status") == "error" else _error("view PNGs not written")
        paths = {}
        try:
            for v in ("iso", "front", "top"):
                local = self._host(job) / f"{job}_views{'_' + highlight if highlight else ''}_{v}.png"
                self.t.get(f"{base}_{v}.png", local)
                paths[v] = str(local)
        except TransportError as e:
            return _error(str(e))
        return {"status": "ok", "paths": paths, "shown": res.get("shown"), "highlight": highlight, "source": "live"}
