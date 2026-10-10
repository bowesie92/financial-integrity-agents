import os
from pathlib import Path
from anthropic import Anthropic

env = Path(os.environ.get("FIA_SECRETS_DIR", "/etc/financial-integrity-agents-secrets")) / "anthropic.env"
for line in env.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

client = Anthropic()
raw = client.messages.with_raw_response.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=50,
    messages=[{"role": "user", "content": "Reply with the single word: ok"}],
)
msg = raw.parse()
print("text:", msg.content[0].text)
print("stop_reason:", msg.stop_reason)
print("input_tokens:", msg.usage.input_tokens, "output_tokens:", msg.usage.output_tokens)
print("workspace_id_header:", raw.headers.get("anthropic-workspace-id"))
print("approx_cost_usd:", round(msg.usage.input_tokens * 1e-6 + msg.usage.output_tokens * 5e-6, 6))
