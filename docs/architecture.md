# Arquitectura

## Estado en la Fase 9

El proyecto es un servidor MCP local escrito en Python. Un cliente MCP lo inicia como proceso local y se comunica con él mediante transporte `stdio`.

```text
Cliente MCP
    ↓ stdio
FastMCP server
    ├── health_check
    │       └── local state + optional guarded STS probe
    ├── listar_recursos_aws
    │       └── AWS inventory
    ├── analizar_actividad_recursos
            └── activity engine
                    ├── common adapter registry
                    ├── free service API signals
                    ├── CloudTrail Event History
                    └── blocked CloudWatch enrichment
    └── diagnosticar_cobertura_aws
            └── diagnostics engine
                    ├── STS and enabled Regions
                    ├── Resource Explorer metadata
                    ├── common adapter registry
                    ├── activity-source availability
                    └── zero-cost operation registry
    ├── analizar_riesgo_costes
    │       └── normalized resources + activity + economic engine
    ├── revisar_free_tier
    │       └── guarded free Free Tier APIs
    └── consultar_costes_aws
            └── exact ephemeral consent
                    └── one guarded Cost Explorer request
```

FastMCP crea el servidor, registra las tools y gestiona el protocolo MCP. Cada tool mantiene su lógica de entrada y presentación separada de `server.py`.

`tools/registry.py` es el registro público y dinámico de tools. El servidor y `health_check` reutilizan esa abstracción, sin inspeccionar atributos internos de FastMCP ni mantener listas duplicadas.

La capa AWS es independiente del servidor MCP. `config.py` resuelve región y perfil sin leer secretos; `aws/session.py` crea sesiones Boto3 sin clientes globales; `aws/inventory.py` agrega y serializa el resultado común.

Boto3 utiliza su cadena estándar de credenciales. El proyecto no lee manualmente claves, tokens ni archivos de credenciales y no realiza llamadas a AWS durante la importación.

STS identifica la cuenta efectiva antes de consultar recursos. Los errores de sesión o identidad son globales. Los fallos posteriores son parciales y se devuelven en `errors` sin descartar los datos disponibles.

El motor de diagnóstico no llama al motor de inventario. Inspecciona las declaraciones del mismo registro de adaptadores, prueba únicamente STS, regiones, metadatos de Resource Explorer y una muestra gratuita de CloudTrail, y conserva CloudWatch bloqueado. Esto separa “servidor operativo” de “cobertura AWS disponible”.

`listar_recursos_aws` valida región, servicios, tipos y texto; transforma errores internos en respuestas seguras y genera un resumen con diagnóstico de cobertura. Cuando hay operaciones medibles pendientes, crea una solicitud efímera en memoria. Una segunda llamada aprueba un subconjunto o cancela sin invocar inventario.

## Pipeline uniforme

El motor ejecuta primero los adaptadores permitidos, con servicios globales antes que regionales, para conservar resultados aunque Resource Explorer agote el presupuesto. Después consulta Resource Explorer, combina las fuentes y aplica una sola deduplicación.

Todos los servicios siguen el mismo recorrido y comparten el mismo esquema. La deduplicación usa ARN, después tipo + región + identificador y, por último, servicio + región + nombre.

```text
Resource Explorer ─┐
                   ├─> modelo común ─> deduplicación ─> resources/resources_by_service
adapter registry ──┘
```

Si Resource Explorer falla, el motor ejecuta todos los adaptadores seleccionados que pueden descubrir recursos. La cobertura registra adaptadores disponibles, seleccionados, ejecutados y fallidos, además de cada operación completada.

## Contrato de adaptadores

Todos implementan `ResourceAdapter` y declaran `AdapterMetadata`: servicio, alcance regional o global, operaciones, tipos soportados, capacidades, campos de detalle e indicadores. Lambda y S3 usan exactamente el mismo registro y motor que EC2, RDS y el resto. No hay listas legacy, fallback privado ni imports directos desde la tool.

El modelo raíz es idéntico para todos. Las diferencias válidas se limitan a `details`. `activity` utiliza el mismo modelo semántico para cualquier servicio y `cost_indicators` contiene únicamente señales potenciales.

## Guard de operaciones

`OperationGuard` consulta el registro central antes de cada llamada SDK. `free` se permite; `unknown` y `write` se bloquean. `potentially_billable` solo se permite con un `ScopedOperationAuthorization` exacto. Este limita operación, región, peticiones y páginas, registra cada petición y no cambia `free-only`.

`InventoryConsentStore` vive únicamente en el proceso MCP. Sus registros expiran, son de un solo uso y guardan hashes de identidad y scope. El inventario provisional se normaliza, anonimiza y limpia de campos sensibles.

## Derivación de permisos IAM

`OperationSpec` es también la fuente de verdad IAM. Cada operación registra las
acciones autorizadoras, capacidad, componente consumidor, tools, alcance,
etapa, coste, riesgo sensible, soporte de ARN, condiciones, dependencias,
alternativas, política destino, consentimiento, justificación y referencia.

```text
registro de operaciones
        ├──> OperationGuard en tiempo de ejecución
        ├──> manifiesto auditable
        └──> generador local determinista
                ├── free-only
                ├── consented-readonly
                ├── combined-readonly
                └── permissions boundary opcional
```

El generador solo concede acciones requeridas o dependientes verificadas. Las
alternativas quedan como documentación. La política IAM establece el máximo
técnico; el guard y los grants efímeros conservan una autorización de
aplicación más estrecha para operaciones potencialmente facturables.

## Pipeline económico

```text
recursos normalizados ──> indicadores potenciales ──┐
actividad común ─────────────────────────────────────┼─> riesgo + prioridad
Free Tier API gratuita ──────────────────────────────┤
Cost Explorer ──> consentimiento exacto ──> 1 página┘
```

`economics/risk.py` no conoce servicios concretos: recibe el mismo `Resource` para Lambda, S3, EC2, RDS y el resto. La actividad se fusiona por identidad normalizada. Free Tier permanece a nivel de cuenta/oferta y no se atribuye artificialmente a un recurso.

El consentimiento de Cost Explorer extiende el store efímero existente mediante un tipo de solicitud. La primera llamada crea estado local sin AWS. En la aprobación, STS vincula la identidad efectiva, el guard autoriza solo `ce:GetCostAndUsage` y el grant se consume antes de la petición. El estado se destruye al terminar o cancelar. Una continuación conserva el token solo en memoria y crea otro consentimiento.

## Pipeline de actividad

```text
recursos normalizados
        ↓
registro común de adaptadores ──> señales gratuitas de APIs
        └───────────────────────> eventos regionales CloudTrail
                                     ↓
                              clasificador central
                                     ↓
                 correlación + confianza + estado conservador
```

Cada adaptador implementa `get_free_activity_signals` mediante la misma interfaz. El motor consulta Event History por región y reutiliza sus páginas; no hace una llamada por recurso. El clasificador central separa lectura, escritura, creación, actualización, borrado, invocación y acceso, y los traduce a uso funcional, actividad administrativa, cambio de configuración, cambio de estado o desconocido.

El resultado conserva fechas diferentes para cada tipo y una `best_known_activity_at` acompañada siempre por `best_known_activity_type`. La correlación solo acepta identificadores de recurso explícitos. Eventos sin relación inequívoca no se atribuyen.

Los límites predeterminados son 100 recursos, 5 regiones, 20 evidencias por recurso, 500 eventos CloudTrail totales y 30 segundos. La paginación usa páginas de hasta 50 eventos. El trabajo es secuencial (`max_concurrency=1`), reutiliza eventos en memoria durante la ejecución y devuelve resultados parciales ante límites o errores.

## Límites actuales

CloudTrail Event History contiene como máximo 90 días de eventos de administración regionales. No equivale a telemetría funcional ni suele incluir eventos de datos como `GetObject`. CloudWatch está preparado como enriquecimiento, pero sus operaciones permanecen bloqueadas por coste. Cost Explorer solo ofrece coste agregado por periodo y servicio en esta fase; no hay forecast, detalle por recurso, billing views personalizadas ni linked accounts. Tampoco se implementan políticas IAM definitivas ni transportes HTTP. La capa solo realiza consultas de lectura y no configura Resource Explorer, trails ni event data stores.

## Principios

- Ejecución local: no hay despliegue en AWS.
- Solo lectura y mínimo privilegio para cualquier acceso futuro a AWS.
- Configuración de credenciales fuera del repositorio.
- Cost Explorer únicamente tras consentimiento efímero exacto y con coste máximo visible.
