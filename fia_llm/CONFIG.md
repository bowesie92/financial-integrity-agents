# LLM configuration (names only, no values)

| Variable | Meaning | Default |
| --- | --- | --- |
| `LLM_PROVIDER` | `anthropic` now; `bedrock` is added at task B7 | `anthropic` |
| `LLM_MODEL` | Registry alias: `dev` (Haiku 4.5), `demo` (Sonnet 5), `demo-plus` (Sonnet 5.5) | `dev` |
| `LLM_STRICT_TOOLS` | `1` adds `strict: true` to every tool. Off until a live call shows it is needed | unset |
| `ANTHROPIC_API_KEY` | Read by the SDK. The value lives in the secrets folder, never in the repo | none |
