"""Tool logic. Transport and config are injected so tests use a fake transport."""
from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path

from . import abaqus_scripts as scripts
from .config import Config
from .logparse import parse_msg, parse_sta
from .security import SecurityError, truncate, validate_filename, validate_host_file, validate_name
from .transport import TransportError

UNREACHABLE = "license server unreachable"


def psq(s: str) -> str:
    """PowerShell single-quoted literal (no expansion; only ' needs doubling)."""
    return "'" + s.replace("'", "''") + "'"


def _error(msg: str, hint: str = "") -> dict:
    return {"status": "error", "error": msg, "hint": hint}


def _traceback(text: str) -> str:
    i = text.find("Traceback (most recent call last)")
    return text[i:].strip() if i >= 0 else ""


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

    # -- tools -------------------------------------------------------------
    def run_script(self, job: str, script_path: str, timeout: int | None = None) -> dict:
        """Executes arbitrary Python in Abaqus/CAE on the VM: uploads a .py to the job dir and runs
        `abaqus cae noGUI=<script>`."""
        try:
            if (g := self._guard()):
                return g
            src = validate_host_file(script_path)
            d = self._prep(job)
            name = self._upload(job, src)
            r = self._abq(d, f"cae noGUI={name}", timeout or self.cfg.script_timeout)
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        tb = _traceback(r.stderr) or _traceback(r.stdout)
        ok = r.returncode == 0 and not tb and not r.timed_out
        out = {"status": "ok" if ok else "error", "exit_code": r.returncode, "timed_out": r.timed_out,
               "stdout": r.stdout, "stderr": r.stderr, "traceback": tb, "elapsed_s": round(r.elapsed, 1)}
        if not ok:
            out["error"] = "timeout" if r.timed_out else (tb.splitlines()[-1] if tb else "script failed")
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
                if w.returncode != 0 or not _json_from(w.stdout):
                    return _error("writing the input file from the .cae failed",
                                  _traceback(w.stderr + w.stdout) or truncate(w.stderr, 2000))
                inp = f"{job}.inp"
            # stale files from an earlier run would fake a status (prior-art: rutwikg _clear_stale)
            stale = ",".join(psq(f"{job}{e}") for e in (".lck", ".sta", ".msg", ".dat", ".odb"))
            self.t.run(f"Set-Location -LiteralPath {psq(d)}; Remove-Item -ErrorAction SilentlyContinue "
                       f"{stale}; exit 0", self.cfg.ssh_timeout)
            cmd = f"job={job} input={inp} cpus={int(cpus)} interactive"
            if background:
                # Win32_Process.Create: the child is not tied to the ssh session (Start-Process
                # children die when it closes, see .critic/review-1.md)
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
        """Status from .sta, .msg and .lck. The exit code is not trusted (prior-art)."""
        try:
            d = self._vm(job)
            def part(tag, f):
                return f"'==={tag}==='; if (Test-Path {psq(f)}) {{ Get-Content {psq(f)} }}; "
            cmd = (f"Set-Location -LiteralPath {psq(d)}; " + part("STA", f"{job}.sta") + part("MSG", f"{job}.msg")
                   + f"'===LCK==='; if (Test-Path {psq(job + '.lck')}) {{ 'yes' }}; '===END==='")
            r = self.t.run(cmd, self.cfg.ssh_timeout)
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        if r.returncode != 0 and "===STA===" not in r.stdout:
            return _error("cannot read job directory", r.stderr.strip())
        parts = {}
        cur = None
        for line in r.stdout.splitlines():
            if line.strip() in ("===STA===", "===MSG===", "===LCK===", "===END==="):
                cur = line.strip().strip("=")
                parts[cur] = []
            elif cur:
                parts[cur].append(line)
        sta_t, msg_t = "\n".join(parts.get("STA", [])), "\n".join(parts.get("MSG", []))
        locked = "yes" in parts.get("LCK", [])
        sta, msg = parse_sta(sta_t), parse_msg(msg_t)
        status = sta["status"]
        if status != "completed":
            if msg["n_errors"]:
                status = "failed"
            elif locked:
                status = "running"
            elif not sta_t.strip() and not msg_t.strip():
                status = "not_found"
        out = {"status": status, "job": job, "locked": locked, "errors": msg["errors"],
               "warnings": msg["warnings"], "n_warnings": msg["n_warnings"]}
        out.update({k: v for k, v in sta.items() if k != "status"})
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
            return _error("no JSON file from Abaqus", _traceback(r.stderr + r.stdout) or truncate(r.stderr, 2000))
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

    def model_info(self, job: str, cae_file: str | None = None) -> dict:
        """Parts, sets, steps and materials of a .cae: cae_file is a host path (with a directory part,
        or ~) that is uploaded, or a bare name already in the VM job dir. Default <job>.cae."""
        try:
            if (g := self._guard()):
                return g
            self._prep(job)
            cae = f"{job}.cae"
            if cae_file:
                cae = self._cae(job, cae_file)
            res = self._python_json(job, scripts.model_info(cae, "_model_info.json"), "_model_info.py", cae=True)
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        res.setdefault("status", "ok")
        return res

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
                return _error("viewport PNG not written", _traceback(r.stderr + r.stdout) or truncate(r.stderr, 2000))
            local = self._host(job) / f"{base}.png"
            self.t.get(f"{d}\\{base}.png", local)
        except (SecurityError, TransportError) as e:
            return _error(str(e))
        return {"status": "ok", "path": str(local)}
