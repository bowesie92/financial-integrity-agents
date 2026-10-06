"""Kill switch. A run stops cleanly, after its current step, when any of these happens:
the kill file exists, or the process gets Ctrl+C or SIGTERM. A second Ctrl+C is not caught, so a run
that is stuck in a long call can still be interrupted by hand."""
import os
import signal
from pathlib import Path

DEFAULT_PATH = Path(os.environ.get("FIA_KILL_FILE") or Path(__file__).resolve().parent.parent / ".fia_kill")


class KillSwitch:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)
        self._flag = None
        self._old = {}

    def is_set(self):
        return self._flag is not None or self.path.exists()

    def reason(self):
        return self._flag or (f"kill file {self.path}" if self.path.exists() else None)

    def trigger(self, why="requested"):
        self._flag = why

    def install_signals(self):
        """Call once from the command that starts a run (main thread only)."""
        def handler(signum, _frame):
            self._flag = signal.Signals(signum).name
            signal.signal(signum, self._old.get(signum, signal.SIG_DFL))   # second signal acts normally
        for s in (signal.SIGINT, signal.SIGTERM):
            self._old[s] = signal.signal(s, handler)

    def restore_signals(self):
        for s, old in self._old.items():
            signal.signal(s, old)
        self._old = {}
