# Fiabilidad y límites

Cada inventario tiene un presupuesto total de tiempo (`timeout_seconds`, entre 1 y 120 segundos) y un presupuesto conservador de llamadas SDK, `AWS_MCP_MAX_REQUESTS_PER_TOOL` (250 por defecto). El guard verifica ambos antes de invocar Boto3; no aumenta reintentos ni pagina fuera del permiso.

Al agotarse el tiempo se devuelve `partial_timeout`; al agotarse las peticiones se devuelve `partial_request_budget_exhausted`. Ambos conservan los recursos ya normalizados y enumeran adaptadores que quedaron sin comprobar. Ninguno significa que el servicio esté vacío.

El contador `sdk_requests_executed` mide llamadas lógicas que el guard llegó a invocar. Botocore puede reintentar una petición de red internamente, por lo que no se presenta como número exacto de intentos HTTP. Los contadores facturables continúan separados: tipos de operación únicos y peticiones autorizadas.

La ejecución es secuencial (`max_concurrency=1`). Los servicios globales se ejecutan una sola vez y los regionales una vez por región. Un fallo de adaptador, `AccessDenied`, endpoint no disponible o timeout se normaliza y no descarta resultados de otros adaptadores.
