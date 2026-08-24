# Codex demo

1. Ask: “Is the MCP working?”
2. Ask: “What resources do I have in eu-west-1?”
3. If the response is `partial_pending_consent`, explain the exact pending
   services, maximum requests, and that none ran; approve only after an
   explicit user answer.
4. Ask: “Which resources could generate costs?”
5. Ask: “Which resources show no recent known activity?”
6. Ask: “How is my Free Tier?”

The standard demo intentionally stops before executing Cost Explorer. Asking
for actual spend produces `pending_consent`; approval is a separate,
single-use decision because its API can be billable.
