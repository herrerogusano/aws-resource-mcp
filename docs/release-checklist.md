# Release checklist — v0.1.0

## Local verification

```powershell
uv sync --locked
uvx ruff format --check src tests
uvx ruff check src tests
uv run python -m compileall -q src
uv run aws-resource-mcp-generate-iam --check
uv run pytest -q
```

The expected result is a clean command sequence and 254 passing tests. GitHub
Actions repeats these checks for pull requests and `master`, without AWS
credentials or API calls.

## Manual MCP smoke test

Use Codex with `uv run aws-resource-mcp` over stdio, then ask:

1. “Is the MCP working?”
2. “What resources do I have in eu-west-1?”
3. “Why is the inventory partial?” when consent is pending.
4. “Which resources could generate costs?”
5. “Which resources have no recent known activity?”
6. “How is my Free Tier?”

The standard demo must not approve Cost Explorer. A pending consent is the
expected safe outcome for any potentially billable operation.

## Release boundaries

This v1 is local, read-only, and `free-only` by default. It does not create
AWS resources, modify IAM, enable AWS services, keep consent after restart, or
claim that missing evidence proves a resource is unused or cost-free.
