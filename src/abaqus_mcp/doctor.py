"""`abaqus-mcp --check`: one line per setup item, OK / FAIL / INFO, with a fix for each FAIL.
Exits 1 when any item fails. Commands go through the configured transport, so the same check
covers native Windows and the VM."""
from __future__ import annotations

import json
import platform
import socket
from pathlib import Path

from . import config, transport
from .service import psq

PLUGIN = "abaqus_plugins\\mcp_live\\mcp_live_plugin.py"


def _line(state: str, item: str, text: str, fix: str = "") -> bool:
    print(f"{state:<5} {item:<16} {text}")
    if fix:
        print(f"{'':<23}fix: {fix}")
    return state != "FAIL"


def _registered() -> bool | None:
    """True when ~/.claude.json has a user-scope server named abaqus; None without the file."""
    p = Path.home() / ".claude.json"
    try:
        return "abaqus" in json.loads(p.read_text(encoding="utf-8-sig")).get("mcpServers", {})
    except (OSError, ValueError):
        return None


def main() -> int:
    cfg = config.load()
    t = transport.make(cfg)
    local = cfg.transport == "local"
    ok = _line("INFO", "machine", f"{platform.system()} {platform.release()}, transport {cfg.transport}"
               + ("" if local else f" (ssh host {cfg.ssh_host})"))

    cmd = cfg.abaqus_cmd
    r = t.run(f"if (-not (Test-Path -LiteralPath {psq(cmd)})) {{ 'MISSING'; exit 0 }}; "
              f"& {psq(cmd)} information=release 2>&1 | Select-String -Pattern '^Abaqus [0-9]' | Select-Object -First 1",
              120)
    out = r.stdout.strip()
    if r.returncode != 0 and not out:
        ok &= _line("FAIL", "Abaqus command", f"cannot run commands: {(r.stderr.strip() or 'timeout')[:200]}",
                    "start the VM and check ssh" if not local else "check that powershell.exe starts")
    elif "MISSING" in out:
        ok &= _line("FAIL", "Abaqus command", f"not found: {cmd}",
                    "in a terminal run `where.exe abaqus`; put that path in config.local.toml as abaqus_cmd = '...'")
    else:
        _line("OK", "Abaqus command", f"{cmd} ({out.splitlines()[-1].strip() if out else 'release not printed'})")

    if not cfg.license_host:
        _line("INFO", "licence", "no licence host known: probe skipped",
              "if jobs fail with a licence error, set license_host (and license_port) in config.local.toml")
    else:
        try:
            with socket.create_connection((cfg.license_host, cfg.license_port), timeout=cfg.probe_timeout):
                _line("OK", "licence", f"{cfg.license_host}:{cfg.license_port} reachable")
        except OSError:
            ok &= _line("FAIL", "licence", f"{cfg.license_host}:{cfg.license_port} not reachable",
                        "connect the university VPN" + ("" if local else " (bin/abaqus-vpn up)"))

    work = cfg.work_vm
    r = t.run(f"try {{ New-Item -ItemType Directory -Force -Path {psq(work)} -ErrorAction Stop | Out-Null; "
              f"$f=Join-Path {psq(work)} '.mcp-write-test'; Set-Content -LiteralPath $f -Value x -ErrorAction Stop; "
              "Remove-Item -LiteralPath $f; 'WRITABLE' } catch { $_.Exception.Message }", 60)
    if "WRITABLE" in r.stdout:
        _line("OK", "work folder", f"{work} writable")
    else:
        ok &= _line("FAIL", "work folder", f"{work}: {(r.stdout.strip() or r.stderr.strip())[:200]}",
                    "set work_vm in config.local.toml to a folder you can write, with no spaces or "
                    "accents in the path (e.g. 'D:\\abaqus-work'), then run setup again")

    r = t.run(f"if (Test-Path -LiteralPath (Join-Path $env:USERPROFILE {psq(PLUGIN)})) {{ 'YES' }}; "
              f"$h={psq(work + chr(92) + 'live' + chr(92) + 'heartbeat.txt')}; "
              "if (Test-Path -LiteralPath $h) { try { \"$([math]::Round([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000 "
              "- [double](Get-Content -LiteralPath $h -Raw), 1))\" } catch { } }", 60)  # invariant culture, as in service
    lines = r.stdout.split()
    if "YES" in lines:
        age = next((float(x) for x in lines if x.lstrip("-").replace(".", "", 1).isdigit()), None)
        live = "a CAE window is connected" if age is not None and age <= cfg.live_stale_s else "no CAE window open now"
        _line("OK", "live plug-in", f"installed; {live}")
    else:
        _line("INFO", "live plug-in", "not installed: cae_live needs it",
              "run setup-windows.cmd again" if local else "./setup.sh live")

    skill = Path.home() / ".claude" / "skills" / "abaqus-modelling" / "SKILL.md"
    _line("OK" if skill.is_file() else "INFO", "skill", str(skill.parent) + ("" if skill.is_file() else " missing"),
          "" if skill.is_file() else ("run setup-windows.cmd again" if local else "see README, Install step 8"))

    reg = _registered()
    if reg:
        _line("OK", "Claude Code", "MCP server 'abaqus' registered (user scope)")
    else:
        _line("INFO", "Claude Code", "MCP server 'abaqus' not registered" if reg is False else "no ~/.claude.json found",
              "install Claude Code, then run setup-windows.cmd again" if local
              else "see README, Install step 7")
    print("all checks passed" if ok else "some checks FAILED: see the fix lines above")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
