"""Abaqus/CAE GUI plug-in of the abaqus-mcp live bridge. Loads at CAE start-up from
<home>\\abaqus_plugins\\mcp_live\\. A FOX timer (FXApp.addTimeout, one-shot, re-armed) ticks every
500 ms: heartbeat file every 1 s, and each script in the inbox goes to the kernel with sendCommand
once no GUI mode (dialog or procedure) is active. No socket is opened."""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)

from abaqusGui import *  # noqa: F401,F403  (FXObject, FXMAPFUNC, SEL_TIMEOUT, getAFXApp, sendCommand, ...)
import mcp_live_core as core

TICK_MS = 500
_modes_active = [0]
_errors = []


def _count_modes():
    """Best effort: count active GUI modes by wrapping activate/deactivate of the documented classes."""
    for cls in (AFXForm, AFXProcedure):
        for name, delta in (("activate", 1), ("deactivate", -1)):
            orig = getattr(cls, name, None)
            if orig is None or getattr(orig, "_mcp_wrapped", False):
                continue

            def make(orig=orig, delta=delta):
                def wrapped(self, *a, **k):
                    _modes_active[0] = max(0, _modes_active[0] + delta)
                    return orig(self, *a, **k)
                wrapped._mcp_wrapped = True
                return wrapped
            setattr(cls, name, make())


def gui_idle():
    return _modes_active[0] == 0


class LiveTicker(FXObject):
    ID_TICK = getattr(FXObject, "ID_LAST", 1000) + 17

    def __init__(self):
        FXObject.__init__(self)
        FXMAPFUNC(self, SEL_TIMEOUT, LiveTicker.ID_TICK, LiveTicker.onTick)
        core.ensure_dirs()
        self.disp = core.Dispatcher(_HERE, lambda cmd: sendCommand(cmd, False, False), gui_idle)
        self.n = 0
        self.arm()

    def arm(self):
        getAFXApp().addTimeout(TICK_MS, self, FXSEL(SEL_TIMEOUT, LiveTicker.ID_TICK))

    def onTick(self, sender, sel, ptr):
        try:
            self.n += 1
            if self.n % 2 == 0:
                core.write_heartbeat()
            self.disp.tick()
        except Exception as e:  # never let the timer die
            _errors.append(repr(e))
        self.arm()
        return 1


_count_modes()
_ticker = LiveTicker()

# registration command (a *_plugin.py file must hold one): a menu entry that prints the bridge state
getAFXApp().getAFXMainWindow().getPluginToolset().registerKernelMenuButton(
    buttonText="MCP live bridge: status", moduleName="mcp_live_kernel", functionName="status()",
    applicableModules=ALL)
