# Estrategia de pruebas

La suite local no contacta AWS por defecto. Usa `Mock`, sesiones simuladas y respuestas Boto3 reducidas; las comprobaciones reales de cuenta siguen siendo manuales y requieren permiso explícito cuando una operación puede facturarse.

- `tests/unit`: comportamiento aislado de modelos, guard, consentimiento y tools.
- `tests/integration`: flujos locales entre componentes y MCP por `stdio`.
- `tests/contract`: el mismo contrato aplicado a todos los adaptadores.
- `tests/safety`: pruebas negativas para escrituras, lecturas sensibles y políticas.
- `tests/performance`: regresiones ligeras de normalización y deduplicación.

Los gates mínimos son formato Ruff, lint, compilación, todos los tests y `aws-resource-mcp-generate-iam --check`. Las pruebas MCP inician un proceso local, hacen `initialize`, `tools/list` y una llamada de health sin AWS; así se comprueba que ningún log contamina `stdout`, que pertenece al protocolo.

No se persigue una cobertura artificial del 100 %. Se priorizan el guard, el registro, consentimiento, límites, paginación, errores parciales y generación IAM. Los tests de red real, si se añaden en el futuro, deberán llevar una marca opt-in y quedar excluidos de CI.
