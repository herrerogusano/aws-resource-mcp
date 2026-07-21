# Arquitectura

## Estado en la Fase 3

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
            ├── Lambda
            └── S3
```

FastMCP crea el servidor, registra las tools y gestiona el protocolo MCP. Cada tool mantiene su lógica de entrada y presentación separada de `server.py`.

La capa AWS es independiente del servidor MCP. `config.py` resuelve región y perfil sin leer secretos; `aws/session.py` crea sesiones Boto3 sin clientes globales; cada servicio tiene un módulo propio; `aws/inventory.py` agrega y serializa el resultado.

Boto3 utiliza su cadena estándar de credenciales. El proyecto no lee manualmente claves, tokens ni archivos de credenciales y no realiza llamadas a AWS durante la importación.

STS identifica la cuenta efectiva antes de consultar recursos. Lambda usa el paginador de `ListFunctions`. S3 lista buckets a nivel de cuenta y consulta sus regiones individualmente; una ubicación nula se normaliza como `us-east-1`.

Los errores de sesión o identidad son globales. Los fallos posteriores de Lambda o S3 son parciales y se devuelven en `errors` sin descartar los datos disponibles.

`listar_recursos_aws` valida región y servicios, solicita únicamente los inventarios seleccionados, transforma errores internos en respuestas seguras y genera un resumen. El diagnóstico Python directo continúa reutilizando el mismo agregador.

## Límites actuales

No se implementan todavía `revisar_free_tier`, políticas IAM definitivas ni transportes HTTP, SSE o Streamable HTTP. La capa AWS solo realiza las consultas de lectura previstas y no accede al contenido de recursos.

## Principios

- Ejecución local: no hay despliegue en AWS.
- Solo lectura y mínimo privilegio para cualquier acceso futuro a AWS.
- Configuración de credenciales fuera del repositorio.
- Sin uso de Cost Explorer.
