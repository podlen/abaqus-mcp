"""GUI-side logic of the live bridge, free of Abaqus imports so it can be tested without CAE.

Layout of the live directory (default C:\\abaqus-work\\live, env ABAQUS_MCP_LIVE_DIR):
  inbox/<id>.py   script uploaded by the MCP (arrives as .part, renamed to .py when complete)
  outbox/<id>.json result written by mcp_live_kernel.run
  log/<id>.py     every script that was run, kept
  heartbeat.txt   epoch seconds (float), rewritten about every second
"""
import os
import re
import time

LIVE_DIR = os.environ.get("ABAQUS_MCP_LIVE_DIR", "C:\\abaqus-work\\live")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_BUSY_S = 3600  # an in-flight script that never answers blocks the queue at most this long


def ensure_dirs(live=LIVE_DIR):
    for sub in ("inbox", "outbox", "log"):
        os.makedirs(os.path.join(live, sub), exist_ok=True)


def write_heartbeat(live=LIVE_DIR, now=None):
    tmp = os.path.join(live, "heartbeat.tmp")
    with open(tmp, "w") as fh:
        fh.write("%.3f" % (time.time() if now is None else now))
    os.replace(tmp, os.path.join(live, "heartbeat.txt"))


def kernel_command(kernel_dir, script_path, out_path):
    """One command string for sendCommand: put the plug-in dir on the kernel path, run the wrapper."""
    return ("import sys\n"
            "if %r not in sys.path: sys.path.append(%r)\n"
            "import mcp_live_kernel\n"
            "mcp_live_kernel.run(%r, %r)" % (kernel_dir, kernel_dir, script_path, out_path))


class Dispatcher:
    """Takes at most one script at a time from the inbox and hands it to `send(command)` once `idle()`."""

    def __init__(self, kernel_dir, send, idle, live=LIVE_DIR, clock=time.time):
        self.kernel_dir, self.send, self.idle, self.live, self.clock = kernel_dir, send, idle, live, clock
        self.inflight = None  # (id, started)

    def _pending(self):
        d = os.path.join(self.live, "inbox")
        names = sorted(n for n in os.listdir(d) if n.endswith(".py") and ID_RE.match(n[:-3]))
        return names

    def tick(self):
        """Returns the id of the script that was sent, else None."""
        if self.inflight:
            sid, t0 = self.inflight
            if os.path.exists(os.path.join(self.live, "outbox", sid + ".json")) or self.clock() - t0 > MAX_BUSY_S:
                self.inflight = None
            else:
                return None
        names = self._pending()
        if not names or not self.idle():
            return None
        sid = names[0][:-3]
        logged = os.path.join(self.live, "log", sid + ".py")
        os.replace(os.path.join(self.live, "inbox", names[0]), logged)
        self.inflight = (sid, self.clock())
        self.send(kernel_command(self.kernel_dir, logged, os.path.join(self.live, "outbox", sid + ".json")))
        return sid
