# Interview narrative

AWS CLI exposes infrastructure data but requires users to know services and
commands. This project makes those questions accessible through Codex and an
MCP server: Codex selects an intent-specific tool, the tool passes through the
central guard and consent validation, adapters normalize safe Boto3 reads, and
the result explains coverage rather than pretending missing data is empty.

The key trade-off is safety over completeness: reads only, least-privilege IAM,
free-only by default, explicit one-use consent for potentially billable APIs,
bounded time and request budgets, and sanitized results. It is robust through
partial errors, multi-region coverage, pagination limits, structured errors,
and local integration/security tests.
