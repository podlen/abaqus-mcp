"""Build the C4 test .cae files on the VM and fetch them to <project>/<job>/, project ~/abaqus-advice.
Run: uv run python tests/advice/build.py [job ...]   (needs VM, license VPN, config.local.toml)."""
import json
import sys
from pathlib import Path

from abaqus_mcp import config
from abaqus_mcp.service import Service
from abaqus_mcp.transport import SshTransport

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
cfg = config.load()
svc = Service(cfg, SshTransport(cfg.ssh_host, cfg.max_output, cfg.ssh_config))
PROJECT = Path.home() / "abaqus-advice"
svc.set_project(str(PROJECT))

for job, script, cae in (("advice-billet", "build_billet.py", "advice_billet.cae"),
                         ("advice-plate", "build_plate.py", "advice_plate.cae"),
                         ("advice-cylinder", "build_cylinder.py", "advice_cylinder.cae"),
                         ("advice-strip", "build_strip.py", "advice_strip.cae"),
                         ("advice-roller", "build_roller.py", "advice_roller.cae")):
    if sys.argv[1:] and job not in sys.argv[1:]:
        continue
    r = svc.run_script(job, str(HERE / script))
    print(job, r["status"], r.get("error", ""), r["traceback"])
    if r["status"] != "ok":
        raise SystemExit(1)
    local = PROJECT / job / cae
    svc.t.get(f"{svc._vm(job)}\\{cae}", local)
    s = svc.model_summary(job, str(local), live=False)
    out = PROJECT / job / (cae[:-4] + "_summary.json")
    out.write_text(json.dumps(s, indent=1))
    print(local, out, s.get("status"))
