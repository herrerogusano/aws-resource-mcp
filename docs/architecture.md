# Arquitectura

## Estado en la Fase 5

El proyecto es un servidor MCP local escrito en Python. Un cliente MCP lo inicia como proceso local y se comunica con él mediante transporte `stdio`.

```text
Cliente MCP
    ↓ stdio
FastMCP server
    ├── health_check
    └── listar_recursos_aws
            ↓
        AWS inventory
            ├── STS
            ├── enabled Regions
            ├── Resource Explorer (general discovery)
            └── adapter engine
                    └── common adapter registry
```

FastMCP crea el servidor, registra las tools y gestiona el protocolo MCP. Cada tool mantiene su lógica de entrada y presentación separada de `server.py`.

La capa AWS es independiente del servidor MCP. `config.py` resuelve región y perfil sin leer secretos; `aws/session.py` crea sesiones Boto3 sin clientes globales; `aws/inventory.py` agrega y serializa el resultado común.

Boto3 utiliza su cadena estándar de credenciales. El proyecto no lee manualmente claves, tokens ni archivos de credenciales y no realiza llamadas a AWS durante la importación.

STS identifica la cuenta efectiva antes de consultar recursos. Los errores de sesión o identidad son globales. Los fallos posteriores son parciales y se devuelven en `errors` sin descartar los datos disponibles.

`listar_recursos_aws` valida región, servicios, tipos y texto; transforma errores internos en respuestas seguras y genera un resumen con diagnóstico de cobertura. El diagnóstico Python directo continúa disponible.

## Pipeline uniforme

Resource Explorer encuentra recursos generales y obtiene dinámicamente los tipos soportados. El motor ejecuta después todos los adaptadores seleccionados, combina descubrimiento complementario y enriquecimiento, y aplica una sola deduplicación.

Todos los servicios siguen el mismo recorrido y comparten el mismo esquema. La deduplicación usa ARN, después tipo + región + identificador y, por último, servicio + región + nombre.

```text
Resource Explorer ─┐
                   ├─> modelo común ─> deduplicación ─> resources/resources_by_service
adapter registry ──┘
```

Si Resource Explorer falla, el motor ejecuta todos los adaptadores seleccionados que pueden descubrir recursos. La cobertura registra adaptadores disponibles, seleccionados, ejecutados y fallidos, además de cada operación completada.

## Contrato de adaptadores

Todos implementan `ResourceAdapter` y declaran `AdapterMetadata`: servicio, alcance regional o global, operaciones, tipos soportados, capacidades, campos de detalle e indicadores. Lambda y S3 usan exactamente el mismo registro y motor que EC2, RDS y el resto. No hay listas legacy, fallback privado ni imports directos desde la tool.

El modelo raíz es idéntico para todos. Las diferencias válidas se limitan a `details`. `activity.status` permanece en `not_analyzed` hasta una fase posterior y `cost_indicators` contiene únicamente señales potenciales.

## Guard de operaciones

`OperationGuard` consulta el registro central antes de cada llamada SDK. `free` se permite; `potentially_billable` requiere el modo de confirmación y confirmación explícita; `unknown` y `write` se bloquean. El modo predeterminado es `free-only`.

## Límites actuales

No se implementan todavía análisis mediante CloudWatch o CloudTrail, costes reales, estado de Free Tier, `revisar_free_tier`, políticas IAM definitivas ni transportes HTTP. La capa solo realiza consultas de lectura y no configura Resource Explorer.

## Principios

- Ejecución local: no hay despliegue en AWS.
- Solo lectura y mínimo privilegio para cualquier acceso futuro a AWS.
- Configuración de credenciales fuera del repositorio.
- Sin uso de Cost Explorer.
