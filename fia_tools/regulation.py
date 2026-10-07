"""get_regulation(state, topic): read-only lookup of illustrative state tax rules.

Reads reference/regulations.json. Every row carries a source URL and an as-of date, and every
answer repeats the not-legal-advice label so the agent can quote it in a memo.
"""
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "reference" / "regulations.json"
STATES = ("AZ", "TX", "CA")


def _load():
    with open(_PATH, encoding="utf-8") as f:
        return json.load(f)


def topics():
    return sorted({r["topic"] for r in _load()["rows"]})


def base_rate(state):
    """The state use tax base rate as a Decimal (for example 0.056), from the use_tax_rate row. None if unknown."""
    from decimal import Decimal
    for r in _load()["rows"]:
        if r["state"] == (state or "").strip().upper() and r["topic"] == "use_tax_rate" and r.get("rate"):
            return Decimal(str(r["rate"]))
    return None


def get_regulation(state, topic):
    """Return the rows for one state and topic. Unknown input returns an error, never a guess."""
    data = _load()
    st = (state or "").strip().upper()
    tp = (topic or "").strip().lower()
    if st not in STATES:
        return {"error": f"Unknown state '{state}'. Known states: {', '.join(STATES)}."}
    rows = [dict(r) for r in data["rows"] if r["state"] == st and r["topic"] == tp]
    if not rows:
        return {"error": f"No rule on '{topic}' for {st}. Known topics: {', '.join(topics())}."}
    return {"state": st, "topic": tp, "label": data["label"], "rows": rows}
