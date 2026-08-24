# Modelo de errores

Una lista vacía solo representa `EMPTY_RESULT` cuando el adaptador fue consultado correctamente. Los estados relevantes no son equivalentes:

| Situación | Resultado |
| --- | --- |
| Recurso no encontrado por una API concreta | `RESOURCE_NOT_FOUND` estructurado |
| Servicio comprobado sin recursos | `checked` y `resources: []` |
| IAM deniega una operación | `partial_permission_denied` + `access_denied` |
| Presupuesto temporal agotado | `partial_timeout` + `inventory_timeout` |
| Presupuesto de peticiones agotado | `partial_request_budget_exhausted` |
| Endpoint o servicio no disponible | `partial_unavailable` |
| Operación medible no aprobada | `partial_pending_consent` |
| Página posterior no autorizada | `operation_truncated` y continuación nueva |
| Configuración global inválida | `error` estructurado |

Los errores solo contienen servicio, tipo y guía segura. No incluyen trazas, credenciales, tokens, cabeceras, IDs de petición ni respuestas Boto3 crudas.
