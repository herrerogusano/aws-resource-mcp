# Progreso

## Estado actual

Fase 7 implementada: diagnóstico explícito de salud local y cobertura AWS con política zero-cost.

## Incluido

- `health_check(check_aws=True)` compatible con llamada sin argumentos y STS opcional.
- Estados de salud `ok`, `degraded` y `error`; credenciales ausentes no derriban el servidor.
- Identidad reducida a cuenta enmascarada y tipo general de principal.
- Registro dinámico de cuatro tools y diagnóstico del registro común de 13 adaptadores.
- Tool `diagnosticar_cobertura_aws` con filtros de servicio y región.
- Dimensiones `identity`, `regions`, `adapters`, `discovery`, `enrichment`, `activity`, `permissions`, `cost_policy` y `limitations`.
- Resource Explorer diagnosticado sin búsqueda de recursos, creación de índices ni cambios.
- CloudTrail probado con una muestra gratuita; CloudWatch permanece bloqueado.
- Límite de cinco regiones y separación entre política permitida y permiso IAM demostrado.
- Resumen de disponibilidad del diagnóstico en `listar_recursos_aws`, sin ejecutar el diagnóstico completo.

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

Los tests unitarios no se conectan a AWS y cubren también salud sin AWS, STS, credenciales ausentes, anonimización, configuración inválida, regiones habilitadas y omitidas, Resource Explorer agregado/local/no configurado/denegado, adaptadores, actividad, filtros, serialización y registro MCP.

La comprobación manual anonimizada del 2026-07-23 obtuvo `ok` tanto localmente como mediante STS, 18 regiones habilitadas y 13 adaptadores registrados. En la muestra acotada a `eu-west-1`, Resource Explorer fue `partial` porque solo se detectaron índices locales, CloudTrail estuvo disponible y CloudWatch bloqueado. Se contaron 654 tipos soportados dinámicamente. Un cliente MCP real por `stdio` descubrió las cuatro tools y ejecutó `health_check` y `diagnosticar_cobertura_aws`.

La tarea de Codex que ya estaba abierta siguió usando el proceso anterior y confirmó su health check. La configuración actualizada contiene la cuarta tool; Codex necesita una tarea nueva o reinicio para recargar el servidor.

La comprobación real anonimizada del 2026-07-22 validó STS y analizó `eu-west-1` y `us-east-1`. Se observaron recursos de Lambda, S3, EC2, CloudFormation e IAM; RDS no devolvió recursos. Los 35 recursos usaron el mismo esquema: 12 tuvieron una señal reciente y 23 quedaron `unknown`; no aparecieron candidatos inactivos en esa muestra. CloudTrail completó ambas regiones con 8 páginas. El único error agregado fue el bloqueo esperado `cost_permission_required` de las operaciones directas potencialmente facturables. CloudWatch ejecutó 0 operaciones y el número de trails permaneció sin cambios en 0.

No se guardaron identificadores, nombres de recursos, identidad AWS, IPs, access key IDs, parámetros de eventos ni payloads.

## Pendiente

- Fase 8: tool `revisar_free_tier` sin Cost Explorer.
- Política IAM mínima formal, CI e integración final con cliente MCP en fases posteriores.
- Una futura mejora con métricas funcionales requerirá consentimiento efímero limitado por operación, recursos, periodo y número de consultas.

## Bloqueos

Ninguno. Los resultados `unknown` son una consecuencia esperada de no consultar métricas facturables ni eventos de datos.
