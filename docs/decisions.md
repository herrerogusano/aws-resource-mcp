# Decisiones

## D-001 — Python y uv

**Decisión:** usar Python 3.12 o posterior y `uv` para gestionar el proyecto y sus dependencias.

**Motivo:** ofrece un flujo de desarrollo moderno y reproducible para un proyecto Python local.

## D-002 — Ejecución local por stdio

**Decisión:** el servidor MCP se ejecutará localmente mediante transporte `stdio`.

**Motivo:** el servidor está diseñado para ejecutarse como proceso local y no necesita infraestructura remota.

## D-003 — AWS de solo lectura

**Decisión:** cualquier integración futura con AWS será exclusivamente de lectura y con permisos de mínimo privilegio.

**Motivo:** protege la cuenta y limita el alcance operativo del proyecto.

## D-004 — Alcance funcional previsto

**Decisión:** las tools objetivo serán `listar_recursos_aws()` y `revisar_free_tier()`; no se utilizará Cost Explorer.

**Motivo:** mantiene un alcance inicial pequeño, útil y fácil de validar.

## D-005 — Calidad sin CD

**Decisión:** habrá CI de GitHub con lint y tests en cada pull request, pero no CD ni despliegue en AWS.

**Motivo:** el proyecto es local y la automatización necesaria se limita a validar cambios.

## D-006 — SDK oficial de MCP y FastMCP

**Decisión:** usar el SDK oficial de MCP para Python y `FastMCP` para construir el servidor.

**Motivo:** FastMCP permite registrar tools a partir de funciones Python tipadas y documentadas, manteniendo pequeña la infraestructura del servidor.

## D-007 — MCP estable 1.x

**Decisión:** restringir temporalmente la dependencia a `mcp[cli]>=1.27,<2`.

**Motivo:** evita versiones preliminares y cambios incompatibles de una futura versión principal mientras el proyecto evoluciona.

## D-008 — Separación entre servidor y tools

**Decisión:** mantener la inicialización de FastMCP en `server.py` y la lógica de cada tool en módulos dentro de `tools/`.

**Motivo:** permite probar la lógica directamente, sin transporte, red ni un cliente MCP.

## D-009 — Boto3 y cadena estándar de credenciales

**Decisión:** usar Boto3 sin leer ni almacenar claves en el código. La configuración solo admite región y un nombre opcional de perfil.

**Motivo:** delega la resolución segura de credenciales en el mecanismo estándar del SDK y evita duplicar manejo sensible.

## D-010 — Capa AWS independiente de MCP

**Decisión:** separar configuración, sesión, identidad, inventarios por servicio y agregación en módulos Python independientes.

**Motivo:** permite ejecutar y probar el inventario sin iniciar el servidor MCP. La integración se hará en la Fase 3.

## D-011 — STS como validación global

**Decisión:** llamar primero a `sts:GetCallerIdentity`; si no puede identificarse la cuenta, detener el inventario con un error global seguro.

**Motivo:** evita presentar resultados parciales sin saber qué identidad y cuenta se están consultando.

## D-012 — Tolerancia a fallos parciales

**Decisión:** conservar los resultados disponibles cuando falle Lambda, S3 o la consulta de región de un bucket, registrando errores estructurados.

**Motivo:** una carencia puntual de permisos no debe ocultar el inventario que sí pudo obtenerse.

## D-013 — Modelos JSON sencillos

**Decisión:** usar diccionarios tipados y normalización ISO 8601, sin añadir otra librería de modelos.

**Motivo:** el inventario es pequeño, serializable y fácil de integrar posteriormente como respuesta MCP.
