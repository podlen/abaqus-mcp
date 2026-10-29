"""Kernel-side wrapper of the live bridge. The GUI sends `mcp_live_kernel.run(script, out)`; the
result goes to the outbox file because sendCommand returns nothing."""
import io
import json
import os
import sys
import time
import traceback


def run(script_path, out_path):
    t0 = time.time()
    ns = {"__name__": "__main__", "__file__": script_path}
    live = os.path.dirname(os.path.dirname(os.path.abspath(script_path)))  # <live>/inbox/<id>.py
    if live not in sys.path:
        sys.path.append(live)  # abqmcp.py, put there by the MCP
    try:
        exec("from abaqus import *\nfrom abaqusConstants import *\nfrom caeModules import *", ns)
    except Exception:
        pass  # outside CAE (tests): the script gets a bare namespace
    buf = io.StringIO()
    old = sys.stdout, sys.stderr
    res = {"ok": True, "output": "", "traceback": "", "result": None}
    sys.stdout = sys.stderr = buf
    try:
        with open(script_path, encoding="utf-8") as fh:
            code = compile(fh.read(), script_path, "exec")
        exec(code, ns)
    except BaseException:
        res["ok"] = False
        res["traceback"] = traceback.format_exc()
    finally:
        sys.stdout, sys.stderr = old
    res["output"] = buf.getvalue()
    try:
        res["result"] = json.loads(json.dumps(ns.get("result"), default=str))
    except Exception:
        res["result"] = None
    res["elapsed_s"] = round(time.time() - t0, 3)
    # log/<id>.json stays as the done mark for the GUI dispatcher; the MCP deletes outbox/<id>.json once read
    for path in (os.path.splitext(script_path)[0] + ".json", out_path):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(res, fh)
        os.replace(tmp, path)


def status():
    print("mcp_live bridge loaded")
