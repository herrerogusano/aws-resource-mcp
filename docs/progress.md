# Progreso

## Estado actual

Fase 5 implementada: inventario enriquecido mediante un registro uniforme de adaptadores y política zero-cost central.

## Incluido

- Contrato `ResourceAdapter` y registro único de 13 adaptadores.
- Modelo normalizado con `details`, `cost_indicators` y actividad aún no analizada.
- Adaptadores para Lambda, S3, EC2/EBS/VPC, RDS/Aurora, DynamoDB, ECS/Fargate, API Gateway, CloudFormation, SQS, SNS, IAM, CloudFront y Route 53.
- Lambda y S3 migrados sin rutas, campos ni fallback especiales.
- Deduplicación común que combina fuentes y conserva datos no vacíos.
- Fallback uniforme cuando Resource Explorer no está disponible.
- Registro de 51 operaciones Boto3 y guard previo a cada llamada.
- `free-only` predeterminado; peticiones potencialmente facturables bloqueadas.
- Indicadores potenciales con `actual_cost_confirmed=false`.
- Eliminación recursiva de credenciales, entornos, políticas y documentos completos.
- 106 tests unitarios sin conexiones reales a AWS.

## Comprobaciones

```powershell
uv sync
uv run pytest -q
uvx ruff check src tests
uv run python -m compileall -q src
uv run python -m aws_resource_mcp.aws.inventory
```

Los modelos de Botocore validan las 51 operaciones registradas y los parámetros usados por los adaptadores. La comprobación real anonimizada verificó la identidad y ejecutó filtros individuales en `eu-west-1`: Lambda devolvió 1 recurso, EC2 6, y RDS, DynamoDB y ECS 0, todos sin errores de servicio. S3 quedó bloqueado antes de Boto3 con `cost_permission_required`; una búsqueda general separada conservó 1 recurso S3 procedente de Resource Explorer. Todos los recursos comprobaron el mismo esquema y todos los indicadores mantuvieron `actual_cost_confirmed=false`.

## Pendiente

- Actividad y último uso conocido mediante fuentes que se definirán en la fase siguiente.
- Tool `revisar_free_tier` sin Cost Explorer.
- Política IAM mínima formal, CI e integración final con cliente MCP.

## Bloqueos

Ninguno. En `free-only`, los adaptadores S3, SQS y SNS no hacen peticiones directas porque AWS las contabiliza; Resource Explorer puede seguir aportando esos recursos.
