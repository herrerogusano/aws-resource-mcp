# Decisiones

## D-001 — Python y uv

**Decisión:** usar Python 3.12 o posterior y `uv` para gestionar el proyecto y sus dependencias.

**Motivo:** ofrece un flujo de desarrollo moderno y reproducible para un proyecto Python local.

## D-002 — Ejecución local por stdio

**Decisión:** el servidor MCP se ejecutará localmente mediante transporte `stdio`.

**Motivo:** el ejercicio no necesita despliegue ni infraestructura remota.

## D-003 — AWS de solo lectura

**Decisión:** cualquier integración futura con AWS será exclusivamente de lectura y con permisos de mínimo privilegio.

**Motivo:** protege la cuenta y limita el alcance del ejercicio.

## D-004 — Alcance funcional previsto

**Decisión:** las tools objetivo serán `listar_recursos_aws()` y `revisar_free_tier()`; no se utilizará Cost Explorer.

**Motivo:** mantiene un alcance pequeño, útil y compatible con el objetivo del portfolio.

## D-005 — Calidad sin CD

**Decisión:** habrá CI de GitHub con lint y tests en cada pull request, pero no CD ni despliegue en AWS.

**Motivo:** el proyecto es local y la automatización necesaria se limita a validar cambios.
