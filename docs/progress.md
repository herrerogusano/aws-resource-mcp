# Progreso

## Estado actual

Fase 9 implementada: IAM de mínimo privilegio derivado del registro real, con
políticas deterministas, manifiesto auditable, validación negativa y montaje
manual de una identidad dedicada.

## Incluido

- Metadatos IAM verificados para todas las operaciones registradas.
- Políticas separadas `free-only`, `consented-readonly`, combinada y boundary opcional.
- Manifiesto con capacidad, consumidor, alcance, coste, sensibilidad, dependencias, alternativas, exclusión, fecha y referencia.
- Generador local `aws-resource-mcp-generate-iam` sin llamadas AWS.
- Exclusión automática de escrituras, contenido sensible, acciones comodín, coste desconocido y riesgo alto.
- Health y diagnóstico con estado local de políticas, sin inspeccionar IAM remoto.
- Tests de sincronización, determinismo, alcance, consentimientos y ausencia de bypass del guard.
- Guía de rol dedicado con credenciales temporales; ninguna modificación IAM ejecutada.

## Comprobación manual de la fase 9

Un cliente MCP nuevo por `stdio` registró las siete tools. `health_check` sin
AWS confirmó manifiesto cargado, políticas sincronizadas y validación local
correcta. El diagnóstico limitado a Lambda, S3 y EC2 en `eu-west-1` confirmó
18 regiones habilitadas, acciones IAM por adaptador, Lambda y EC2 en
`free-only`, y S3 pendiente de consentimiento. No ejecutó inventario de
adaptadores, actividad, operaciones potencialmente facturables, escrituras ni
llamadas IAM.

Access Analyzer y el simulador no se ejecutaron porque su coste permanece sin
verificar. No se creó ni adjuntó ninguna política.

- Modelo económico común con riesgo, prioridad, coste real, Free Tier, evidencia, limitaciones y recomendaciones.
- Tool `analizar_riesgo_costes`, que reutiliza inventario y actividad sin presentar indicadores como gasto confirmado.
- Tools `revisar_free_tier` y `consultar_costes_aws`; el registro MCP contiene siete tools.
- `GetFreeTierUsage` y `GetAccountPlanState` registrados como lecturas gratuitas con evidencia oficial fechada.
- `GetCostAndUsage`, forecast y detalle por recurso registrados como potencialmente facturables.
- Primera llamada de Cost Explorer sin sesión Boto3 ni llamadas AWS; muestra scope, una petición máxima y estimación de 0,01 USD.
- Grant de Cost Explorer efímero, de un uso, una página y scope exacto; cada continuación exige otra aprobación.
- Identidad vinculada al ejecutar, tokens ocultos, estado sensible destruido y auditoría anonimizada.
- Forecast y detalle por recurso rechazados como operaciones separadas no implementadas, sin ampliar consentimientos.
- Diagnóstico y health check con capacidades económicas y contadores facturables separados.

- Estados explícitos para inventario completo, consentimiento pendiente, timeout, permisos denegados y fuentes no disponibles.
- Solicitudes en memoria con expiración de cinco minutos, identidad y scope vinculados, cancelación y uso único.
- Separación genérica de descubrimiento, enriquecimiento y paginación en el contrato común.
- Autorización central exacta por operación y región, con límites de peticiones.
- S3 `ListBuckets`, SQS `ListQueues` y SNS `ListTopics` como enumeraciones pendientes; los detalles requieren otra aprobación.
- Recuento separado de operaciones potencialmente facturables únicas y peticiones ejecutadas.
- Inventario provisional normalizado y anonimizado; no se conservan respuestas Boto3 crudas.

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

226 tests pasan. No se conectan a AWS y cubren también salud, STS, anonimización, Resource Explorer, adaptadores, actividad, consentimiento, expiración, uso único, identidad, scope, límites, paginación, timeout, deduplicación, filtros, serialización, riesgo económico, Free Tier, Cost Explorer bloqueado/consentido y registro MCP.

La comprobación manual anonimizada del 2026-07-23 ejecutó únicamente operaciones gratuitas. Free Tier devolvió un plan activo de tipo `paid`, 9 ofertas visibles y las 9 `within_limit`; se consultó una página completa con `GetAccountPlanState` y `GetFreeTierUsage`. Un análisis limitado a Lambda/EC2 en `eu-west-1` revisó 7 recursos: la muestra no contenía indicadores potenciales y quedó `none_detected`, que no equivale a coste cero. La primera llamada local de Cost Explorer produjo `pending_consent`, una petición máxima y 0,01 USD estimados. No se aprobó. Operaciones facturables ejecutadas: 0.

Un cliente MCP nuevo por `stdio` confirmó los tres campos de consentimiento en el esquema. La primera llamada real, limitada a una región y anonimizada, conservó 18 recursos de cuatro servicios y devolvió S3, SQS y SNS como pendientes. Cada enumeración indicó un máximo de una petición; se ejecutaron 0 operaciones potencialmente facturables y 0 peticiones de ese tipo. No se realizó la segunda llamada.

La comprobación manual anonimizada del 2026-07-23 obtuvo `ok` tanto localmente como mediante STS, 18 regiones habilitadas y 13 adaptadores registrados. En la muestra acotada a `eu-west-1`, Resource Explorer fue `partial` porque solo se detectaron índices locales, CloudTrail estuvo disponible y CloudWatch bloqueado. Se contaron 654 tipos soportados dinámicamente. Un cliente MCP real por `stdio` descubrió las cuatro tools y ejecutó `health_check` y `diagnosticar_cobertura_aws`.

La tarea de Codex que ya estaba abierta siguió usando el proceso anterior y confirmó su health check. La configuración actualizada contiene la cuarta tool; Codex necesita una tarea nueva o reinicio para recargar el servidor.

La comprobación real anonimizada del 2026-07-22 validó STS y analizó `eu-west-1` y `us-east-1`. Se observaron recursos de Lambda, S3, EC2, CloudFormation e IAM; RDS no devolvió recursos. Los 35 recursos usaron el mismo esquema: 12 tuvieron una señal reciente y 23 quedaron `unknown`; no aparecieron candidatos inactivos en esa muestra. CloudTrail completó ambas regiones con 8 páginas. El único error agregado fue el bloqueo esperado `cost_permission_required` de las operaciones directas potencialmente facturables. CloudWatch ejecutó 0 operaciones y el número de trails permaneció sin cambios en 0.

No se guardaron identificadores, nombres de recursos, identidad AWS, IPs, access key IDs, parámetros de eventos ni payloads.

## Pendiente

- Prueba real limitada de la segunda llamada, después de mostrar y recibir aprobación explícita para su alcance.
- Consulta real de Cost Explorer únicamente si el usuario aprueba después el scope y el coste máximo mostrados.
- Política IAM mínima formal, CI e integración final con cliente MCP en fases posteriores.
- Una futura mejora con métricas funcionales requerirá consentimiento efímero limitado por operación, recursos, periodo y número de consultas.

## Bloqueos

Ninguno. Los resultados `unknown` son una consecuencia esperada de no consultar métricas facturables ni eventos de datos.
