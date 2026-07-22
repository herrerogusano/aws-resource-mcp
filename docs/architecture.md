# Arquitectura

## Estado en la Fase 4

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
            └── Resource Explorer (uniform discovery)
```

FastMCP crea el servidor, registra las tools y gestiona el protocolo MCP. Cada tool mantiene su lógica de entrada y presentación separada de `server.py`.

La capa AWS es independiente del servidor MCP. `config.py` resuelve región y perfil sin leer secretos; `aws/session.py` crea sesiones Boto3 sin clientes globales; `aws/inventory.py` agrega y serializa el resultado común.

Boto3 utiliza su cadena estándar de credenciales. El proyecto no lee manualmente claves, tokens ni archivos de credenciales y no realiza llamadas a AWS durante la importación.

STS identifica la cuenta efectiva antes de consultar recursos. Los errores de sesión o identidad son globales. Los fallos posteriores son parciales y se devuelven en `errors` sin descartar los datos disponibles.

`listar_recursos_aws` valida región, servicios, tipos y texto; transforma errores internos en respuestas seguras y genera un resumen con diagnóstico de cobertura. El diagnóstico Python directo continúa disponible.

## Descubrimiento uniforme

Resource Explorer encuentra recursos generales y obtiene dinámicamente los tipos soportados. Un índice agregador se consulta una sola vez; con índices locales se consulta cada índice accesible y la cobertura se marca como parcial.

Todos los servicios siguen el mismo recorrido y comparten el mismo esquema. La deduplicación usa ARN, después tipo + región + identificador y, por último, servicio + región + nombre.

```text
Resource Explorer ─> normalización ─> deduplicación ─> resources/resources_by_service
```

La cobertura puede ser `complete_for_supported_resources`, `partial` o `unavailable`. Incluso el primer estado se limita a tipos soportados e indexados por Resource Explorer.

## Límites actuales

No se implementan todavía análisis de actividad, `revisar_free_tier`, políticas IAM definitivas ni transportes HTTP. Cualquier detalle futuro por servicio deberá quedar detrás de una interfaz común y conservar el mismo modelo de respuesta. La capa solo realiza consultas de lectura y no configura Resource Explorer.

## Principios

- Ejecución local: no hay despliegue en AWS.
- Solo lectura y mínimo privilegio para cualquier acceso futuro a AWS.
- Configuración de credenciales fuera del repositorio.
- Sin uso de Cost Explorer.
