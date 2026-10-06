"""Tool framework: validation, result envelope, size bounds, untrusted-text labeling.

Implements the principles in docs/tools.md. A tool is a ToolSpec; run_tool() validates the
arguments, calls the handler, bounds the output, and always returns an envelope dict.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import psycopg

REASON_MIN, REASON_MAX = 10, 300
MAX_ROWS = 50
MAX_CHARS = 6000            # limit on the whole envelope sent to the model
ENVELOPE_RESERVE = 400      # room for ok, row_count, truncated and notes around the result
UNTRUSTED_MAX = 200


class ToolError(Exception):
    """Raised by a handler. code is one of invalid_input, not_found, too_large, timeout, internal."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


# ---- parameters ------------------------------------------------------------------------------
@dataclass(frozen=True)
class Param:
    kind: str                 # str, int, number, bool, enum, date, str_list, evidence
    description: str
    required: bool = False
    default: object = None
    min: float | None = None  # value bound, or length bound for str, item count for lists
    max: float | None = None
    choices: tuple = ()
    pattern: str | None = None
    item_max: int = 300       # longest item in a str_list

    def schema(self):
        if self.kind == "str":
            s = {"type": "string"}
            if self.min is not None:
                s["minLength"] = int(self.min)
            if self.max is not None:
                s["maxLength"] = int(self.max)
            if self.pattern:
                s["pattern"] = self.pattern
        elif self.kind == "int":
            s = {"type": "integer"}
            if self.min is not None:
                s["minimum"] = int(self.min)
            if self.max is not None:
                s["maximum"] = int(self.max)
        elif self.kind == "number":
            s = {"type": "number"}
            if self.min is not None:
                s["minimum"] = self.min
            if self.max is not None:
                s["maximum"] = self.max
        elif self.kind == "bool":
            s = {"type": "boolean"}
        elif self.kind == "enum":
            s = {"type": "string", "enum": list(self.choices)}
        elif self.kind == "date":
            s = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
        elif self.kind == "str_list":
            s = {"type": "array", "items": {"type": "string", "maxLength": self.item_max}}
            if self.min is not None:
                s["minItems"] = int(self.min)
            if self.max is not None:
                s["maxItems"] = int(self.max)
        elif self.kind == "evidence":
            s = {"type": "array", "minItems": 1, "maxItems": 20, "items": {
                "type": "object", "additionalProperties": False, "required": ["table", "id"],
                "properties": {"table": {"type": "string"}, "id": {"type": "string"},
                               "note": {"type": "string", "maxLength": 200}}}}
        else:
            raise ValueError(self.kind)
        s["description"] = self.description
        return s


def _fail(msg):
    raise ToolError("invalid_input", msg)


def _check(name, p, v):
    k = p.kind
    if k == "str":
        if not isinstance(v, str):
            _fail(f"'{name}' must be a string")
        if p.min is not None and len(v) < p.min:
            _fail(f"'{name}' must be at least {int(p.min)} characters")
        if p.max is not None and len(v) > p.max:
            _fail(f"'{name}' must be at most {int(p.max)} characters")
        if p.pattern and not re.fullmatch(p.pattern, v):
            _fail(f"'{name}' has the wrong format (expected pattern {p.pattern})")
        return v
    if k in ("int", "number"):
        if isinstance(v, bool) or not isinstance(v, (int, float) if k == "number" else int):
            _fail(f"'{name}' must be {'an integer' if k == 'int' else 'a number'}")
        if p.min is not None and v < p.min:
            _fail(f"'{name}' must be at least {p.min:g}")
        if p.max is not None and v > p.max:
            _fail(f"'{name}' must be at most {p.max:g}")
        return v
    if k == "bool":
        if not isinstance(v, bool):
            _fail(f"'{name}' must be true or false")
        return v
    if k == "enum":
        if v not in p.choices:
            _fail(f"'{name}' must be one of: {', '.join(p.choices)}")
        return v
    if k == "date":
        if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            _fail(f"'{name}' must be a date written YYYY-MM-DD")
        try:
            return date.fromisoformat(v)
        except ValueError:
            _fail(f"'{name}' is not a real date")
    if k == "str_list":
        if not isinstance(v, list) or not all(isinstance(i, str) for i in v):
            _fail(f"'{name}' must be a list of strings")
        if p.min is not None and len(v) < p.min:
            _fail(f"'{name}' needs at least {int(p.min)} item(s)")
        if p.max is not None and len(v) > p.max:
            _fail(f"'{name}' allows at most {int(p.max)} items")
        if any(not i.strip() or len(i) > p.item_max for i in v):
            _fail(f"each item in '{name}' must be 1 to {p.item_max} characters")
        return v
    if k == "evidence":
        if not isinstance(v, list) or not 1 <= len(v) <= 20:
            _fail(f"'{name}' must be a list of 1 to 20 items")
        seen = set()
        for i, item in enumerate(v):
            if not isinstance(item, dict) or set(item) - {"table", "id", "note"} or not {"table", "id"} <= set(item):
                _fail(f"evidence item {i}: use exactly table, id, and optionally note")
            if not isinstance(item["table"], str) or not isinstance(item["id"], str) or not item["id"].strip():
                _fail(f"evidence item {i}: table and id must be strings")
            if "note" in item and (not isinstance(item["note"], str) or len(item["note"]) > 200):
                _fail(f"evidence item {i}: note must be a string of at most 200 characters")
            key = (item["table"], item["id"])
            if key in seen:
                _fail(f"evidence item {i} repeats {item['table']} {item['id']}")
            seen.add(key)
        return v
    raise ValueError(k)


# ---- tools -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    params: dict
    handler: object = field(compare=False)

    def definition(self):
        """The tool definition sent to the model. `reason` is always required."""
        props = {"reason": Param("str", f"Why you are making this call, {REASON_MIN} to {REASON_MAX} "
                                 "characters. It is logged and shown in the transcript.",
                                 required=True, min=REASON_MIN, max=REASON_MAX).schema()}
        required = ["reason"]
        for n, p in self.params.items():
            props[n] = p.schema()
            if p.required:
                required.append(n)
        return {"name": self.name, "description": self.description,
                "input_schema": {"type": "object", "properties": props, "required": required,
                                 "additionalProperties": False}}

    def validate(self, args):
        if not isinstance(args, dict):
            _fail("Arguments must be a JSON object")
        allowed = {"reason", *self.params}
        extra = sorted(set(args) - allowed)
        if extra:
            _fail(f"Unknown argument(s): {', '.join(extra)}. Allowed: {', '.join(sorted(allowed))}")
        reason = args.get("reason")
        if not isinstance(reason, str) or not REASON_MIN <= len(reason.strip()) <= REASON_MAX:
            _fail(f"'reason' is required and must be {REASON_MIN} to {REASON_MAX} characters")
        out = {}
        for n, p in self.params.items():
            if n in args and args[n] is not None:
                out[n] = _check(n, p, args[n])
            elif p.required:
                _fail(f"'{n}' is required")
            elif p.default is not None:
                out[n] = p.default
        return out


@dataclass
class ToolContext:
    conn: object
    run_id: str
    agent: str                 # ap_guardian or gl_sentinel
    dry_run: bool = False      # propose_finding inserts, then rolls back
    finished: bool = False
    finish: dict | None = None


class Registry:
    def __init__(self, tools):
        self._tools = {t.name: t for t in tools}
        if len(self._tools) != len(tools):
            raise ValueError("duplicate tool name")

    def names(self):
        return list(self._tools)

    def definitions(self):
        return [t.definition() for t in self._tools.values()]

    def run(self, ctx, name, args):
        return run_tool(self, ctx, name, args)


# ---- output ----------------------------------------------------------------------------------
def jsonable(v):
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return (v.astimezone(timezone.utc) if v.tzinfo else v).isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v


def clean_untrusted(v):
    """Free text from vendors or users: control characters out, cut to 200 characters."""
    if v is None:
        return None
    s = str(v)
    s = re.sub(r"[\r\n\t  ]", " ", s)
    s = "".join(c for c in s if unicodedata.category(c)[0] != "C")
    return s[:UNTRUSTED_MAX]


def label_untrusted(record, columns):
    """Rename the given columns to untrusted_<name> and clean their text."""
    out = {}
    for k, v in record.items():
        out[f"untrusted_{k}" if k in columns else k] = clean_untrusted(v) if k in columns else v
    return out


def _size(x):
    return len(json.dumps(x, separators=(",", ":"), ensure_ascii=False))


def bound(result):
    """Cap lists at 50 rows and the whole result at 6,000 characters. Returns (result, truncated, notes)."""
    result = jsonable(result)
    truncated, notes = False, []
    for k, v in list(result.items()):
        if isinstance(v, list) and len(v) > MAX_ROWS:
            notes.append(f"'{k}' cut from {len(v)} to {MAX_ROWS} rows")
            result[k] = v[:MAX_ROWS]
            truncated = True
    original = {k: len(v) for k, v in result.items() if isinstance(v, list)}
    while _size(result) > MAX_CHARS - ENVELOPE_RESERVE:
        lists = [(k, v) for k, v in result.items() if isinstance(v, list) and len(v) > 1]
        if not lists:
            raise ToolError("too_large", "The result is too large to return. Narrow the query with filters.")
        k, v = max(lists, key=lambda kv: _size(kv[1]))
        result[k] = v[:-1]          # drop one row at a time so as many rows as fit are kept
        truncated = True
    for k, n in original.items():
        if len(result[k]) < n and not any(f"'{k}' cut" in x for x in notes):
            notes.append(f"'{k}' cut from {n} to {len(result[k])} rows to fit 6,000 characters")
    if truncated:
        notes.append("Result is truncated: narrow the query (period, account, user, date range) to see the rest.")
    return result, truncated, notes


def _row_count(result):
    lists = [v for v in result.values() if isinstance(v, list)]
    if "rows" in result and isinstance(result["rows"], list):
        return len(result["rows"])
    return max((len(v) for v in lists), default=1)


def fail(code, message):
    return {"ok": False, "error": {"code": code, "message": message}}


def run_tool(registry, ctx, name, args):
    spec = registry._tools.get(name)
    if spec is None:
        return fail("not_found", f"Unknown tool '{name}'. Available: {', '.join(registry.names())}")
    try:
        clean = spec.validate(args)
        raw = spec.handler(ctx, clean)
        notes = list(raw.pop("_notes", [])) if isinstance(raw, dict) else []
        result, truncated, more = bound(raw)
        return {"ok": True, "result": result, "row_count": _row_count(result),
                "truncated": truncated, "notes": notes + more}
    except ToolError as e:
        return fail(e.code, e.message)
    except psycopg.errors.QueryCanceled:
        return fail("timeout", "The query took too long. Narrow it with filters.")
    except psycopg.Error as e:
        return fail("internal", f"Database error ({type(e).__name__}). Try a narrower query.")
    except Exception as e:  # never crash the run on a tool bug
        return fail("internal", f"Tool failed ({type(e).__name__}).")


def envelope_json(env):
    """What goes back to the model as the tool_result content."""
    return json.dumps(env, separators=(",", ":"), ensure_ascii=False)
