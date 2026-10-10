"""One real tool round trip against a provider. Costs a fraction of a cent on Haiku.

Usage: python scripts/smoke_provider.py --provider anthropic --model dev --key-var NAME
       [--env-file /etc/financial-integrity-agents-secrets/anthropic.env] [--strict]

Reads the key from the env file by variable NAME and never prints it. Checks that the request
is accepted, the model calls the tool, the tool result goes back, history round-trips, and the
workspace header is present. Exit 0 means every check passed.
"""
import os
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fia_llm import AnthropicClient, FatalLLMError, get_profile  # noqa: E402

TOOL = {"name": "echo_number", "description": "Returns the number it was given.",
        "input_schema": {"type": "object", "additionalProperties": False,
                         "properties": {"n": {"type": "integer"}, "reason": {"type": "string"}},
                         "required": ["n", "reason"]}}


def read_key(path, name):
    for line in Path(path).read_text().splitlines():
        m = re.match(rf"\s*(?:export\s+)?{re.escape(name)}\s*=\s*(.*)$", line)
        if m:
            return m.group(1).strip().strip("'\"")
    raise SystemExit(f"{name} not found in {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--model", default="dev")
    ap.add_argument("--key-var", required=True)
    ap.add_argument("--env-file", default=os.path.join(os.environ.get("FIA_SECRETS_DIR", "/etc/financial-integrity-agents-secrets"), "anthropic.env"))
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    if a.provider != "anthropic":
        raise SystemExit("Only anthropic for now; bedrock is task B7")

    client = AnthropicClient(get_profile(a.model, a.strict or None),
                             api_key=read_key(a.env_file, a.key_var))
    checks, total = [], 0
    history = [{"role": "user", "content": "Call echo_number with n=7, then tell me the number it returned."}]
    try:
        r1 = client.complete("You are a test assistant. Use the tool when asked.", history,
                             tools=[TOOL], max_tokens=1024)
        checks.append(("model asked for the tool", r1.stop_reason == "tool_use" and len(r1.tool_calls) == 1))
        call = r1.tool_calls[0]
        checks.append(("arguments valid, reason present", call.input.get("n") == 7 and bool(call.input.get("reason"))))
        history.append(r1.assistant_message())
        history.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call.id, "content": "7"}]})
        r2 = client.complete("You are a test assistant. Use the tool when asked.", history,
                             tools=[TOOL], max_tokens=1024)
        checks.append(("final answer mentions 7", r2.stop_reason == "end_turn" and "7" in r2.text))
        checks.append(("workspace header present", bool(r1.workspace_id and r2.workspace_id)))
        total = (r1.cost_usd or 0) + (r2.cost_usd or 0)
        print(f"model {r1.model}  workspace {r1.workspace_id}  request ids {r1.request_id}, {r2.request_id}")
        print(f"tokens in/out: {r1.usage.input_tokens}/{r1.usage.output_tokens} then "
              f"{r2.usage.input_tokens}/{r2.usage.output_tokens}  cost about ${total}")
    except FatalLLMError as e:
        print(f"FAILED: {e}")
        return 1
    for label, ok in checks:
        print(("OK   " if ok else "FAIL ") + label)
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
