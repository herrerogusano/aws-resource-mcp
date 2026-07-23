# Diagnóstico y cobertura

## Salud y cobertura no son equivalentes

`health_check` responde si el servidor local, sus registros y su configuración segura pueden funcionar. `diagnosticar_cobertura_aws` responde qué parte de AWS puede examinar y por qué la cobertura puede ser parcial.

Un servidor puede estar operativo aunque no existan credenciales. Del mismo modo, no encontrar recursos solo significa “vacío” cuando la fuente estaba disponible; con permisos denegados o una fuente bloqueada el resultado es desconocido.

## Health check avanzado

`health_check(check_aws=True)` conserva una llamada sin argumentos válida. Devuelve:

- servidor, versión y transporte;
- tools y adaptadores registrados dinámicamente;
- región y modo económico;
- credenciales detectadas y acceso STS, si se solicitó;
- identidad anonimizada;
- cero operaciones potencialmente facturables.

Estados:

- `ok`: configuración local válida y STS correcto cuando se solicitó;
- `degraded`: servidor operativo con AWS inaccesible;
- `error`: registro o configuración interna no inicializable.

Con `check_aws=false` no crea clientes AWS. Con `true` solo usa `sts:GetCallerIdentity` mediante el guard.

## Tool de cobertura

`diagnosticar_cobertura_aws` analiza:

- `identity`: disponibilidad y tipo general de principal;
- `regions`: región predeterminada, habilitadas, solicitadas, comprobadas y omitidas;
- `adapters`: capacidades y operaciones de los 13 adaptadores comunes;
- `discovery`: Resource Explorer y fallback declarado;
- `enrichment`: adaptadores capaces, sin ejecutarlos;
- `activity`: señales propias, CloudTrail y CloudWatch bloqueado;
- `permissions`: comprobaciones reales frente a declaraciones locales;
- `cost_policy`: recuentos por clasificación y operaciones bloqueadas;
- `limitations`: impacto y requisitos para ampliar cobertura.

Estados de cobertura: `available`, `partial`, `unavailable`, `not_configured`, `permission_denied`, `blocked_by_cost_policy`, `not_supported`, `not_checked` y `error`.

## Regiones y límites

La tool reutiliza `ec2:DescribeRegions`, no activa regiones y separa adaptadores globales del conjunto regional. Para mantener la ejecución acotada prueba como máximo cinco regiones y declara las omitidas. Si no puede enumerarlas, conserva la región predeterminada como cobertura parcial.

## Resource Explorer

Solo consulta índices existentes y tipos soportados dinámicamente. No busca recursos, no crea índices ni vistas y no configura agregación.

- agregador accesible: búsqueda multirregional `available`;
- solo índices locales: `partial`;
- API accesible sin índices: `not_configured`;
- acceso denegado: `permission_denied`.

Un agregador ausente se explica como opción que requeriría escritura; la tool no ordena crearlo ni ejecuta cambios.

## Adaptadores y permisos

Todos los servicios, incluidos Lambda y S3, se inspeccionan desde el mismo registro. Una operación puede estar registrada y permitida por `free-only` sin que el diagnóstico afirme haber demostrado su permiso IAM. Para probar todos los permisos habría que ejecutar inventarios, algo deliberadamente excluido.

S3, SQS y SNS pueden aparecer bloqueados por la política económica actual. Esto describe cobertura desconocida o limitada, no ausencia de recursos. La revisión de consultas de inventario de bajo volumen queda como criterio de cierre.

## Fuentes de actividad

La comprobación de CloudTrail usa como máximo un `LookupEvents` con un resultado en una región y conserva el límite conceptual de 90 días. No devuelve eventos. CloudWatch permanece `blocked_by_cost_policy`, con `executed=false` y consentimiento requerido.

## Resultado manual anonimizado

El 2026-07-23:

- salud local y STS: `ok`;
- regiones habilitadas: 18;
- adaptadores registrados: 13;
- muestra: `eu-west-1`;
- Resource Explorer: `partial`, sin agregador detectado;
- tipos soportados obtenidos dinámicamente: 654;
- CloudTrail: `available`;
- CloudWatch: `blocked_by_cost_policy`;
- operaciones potencialmente facturables ejecutadas: 0.

Un cliente MCP por `stdio` descubrió las cuatro tools y ejecutó las dos tools diagnósticas. La tarea de Codex ya abierta confirmó el proceso anterior; la cuarta tool requiere que Codex recargue la configuración en una tarea nueva o tras reinicio.

## Preguntas compatibles

- ¿Está funcionando el MCP aunque AWS no responda?
- ¿Qué regiones puede comprobar?
- ¿Existe un índice agregador?
- ¿Qué adaptadores están registrados y cuáles bloquea la política?
- ¿CloudTrail está disponible?
- ¿Por qué la cobertura es parcial?
- ¿Se ejecutó alguna operación potencialmente facturable?
