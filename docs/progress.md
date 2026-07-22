# Progreso

## Estado actual

Fase 6 implementada: análisis uniforme de actividad y último indicio conocido con política zero-cost.

## Incluido

- Tool MCP `analizar_actividad_recursos` con filtros por servicio, región e identificador.
- Modelo común con estados, tipos de actividad, confianza, evidencia y limitaciones.
- Fechas separadas para uso funcional, actividad administrativa, configuración y estado.
- Clasificador central de eventos: lectura, escritura, creación, actualización, borrado, invocación, acceso y desconocido.
- `cloudtrail:LookupEvents` regional, paginado, anonimizado, limitado a 90 días y reutilizado entre recursos.
- Presupuesto de eventos repartido entre regiones para evitar que la primera agote toda la cobertura.
- Contrato `get_free_activity_signals` en los 13 adaptadores mediante el registro existente.
- Creación, estado y campos declarados por adaptador como señales gratuitas; ninguna ruta especial para Lambda o S3.
- Candidatos inactivos conservadores y resultados `unknown` ante datos insuficientes.
- `include_activity_summary` opcional en `listar_recursos_aws`, sin análisis profundo ni nuevas llamadas.
- CloudWatch preparado como enriquecimiento pero bloqueado antes de Boto3.
- Límites configurables de recursos, regiones, evidencias y tiempo; caché de eventos solo en memoria.
- Errores y resultados parciales sin descartar otros servicios o regiones.

## Comprobaciones

```powershell
uv sync
uvx ruff format --check src tests
uvx ruff check src tests
uv run pytest -q
uv run python -m compileall -q src
```

Los tests unitarios no se conectan a AWS y cubren modelo, fechas, serialización, CloudTrail vacío y paginado, límite de 90 días, regiones, permisos, ambigüedad, anonimización, adaptadores, uniformidad, clasificación, inactividad, bloqueo económico, tool y registro MCP.

La comprobación real anonimizada del 2026-07-22 validó STS y analizó `eu-west-1` y `us-east-1`. Se observaron recursos de Lambda, S3, EC2, CloudFormation e IAM; RDS no devolvió recursos. Los 35 recursos usaron el mismo esquema: 12 tuvieron una señal reciente y 23 quedaron `unknown`; no aparecieron candidatos inactivos en esa muestra. CloudTrail completó ambas regiones con 8 páginas. El único error agregado fue el bloqueo esperado `cost_permission_required` de las operaciones directas potencialmente facturables. CloudWatch ejecutó 0 operaciones y el número de trails permaneció sin cambios en 0.

No se guardaron identificadores, nombres de recursos, identidad AWS, IPs, access key IDs, parámetros de eventos ni payloads.

## Pendiente

- Fase 7: tool `revisar_free_tier` sin Cost Explorer.
- Política IAM mínima formal, CI e integración final con cliente MCP en fases posteriores.
- Una futura mejora con métricas funcionales requerirá consentimiento efímero limitado por operación, recursos, periodo y número de consultas.

## Bloqueos

Ninguno. Los resultados `unknown` son una consecuencia esperada de no consultar métricas facturables ni eventos de datos.
