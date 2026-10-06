"""One JSONL file per run: one JSON object per line, written and flushed as things happen, so a run
that dies still leaves its record. Nothing secret goes in: settings, ids and usage only. The tool
results are logged in full (they are already capped at 6,000 characters)."""
import json
from datetime import datetime, timezone

from fia_tools.framework import jsonable


class RunLog:
    def __init__(self, path=None, keep=False):
        """path=None writes no file. keep=True also keeps the events in memory (tests)."""
        self._fh = open(path, "a", encoding="utf-8") if path else None
        self.events = [] if keep else None
        self._seq = 0

    def event(self, kind, **fields):
        self._seq += 1
        rec = {"seq": self._seq, "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
               "event": kind, **jsonable(fields)}
        if self.events is not None:
            self.events.append(rec)
        if self._fh:
            self._fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            self._fh.flush()

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None
