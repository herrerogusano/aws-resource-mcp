# AWS Resource MCP

Servidor MCP local, desarrollado en Python, para consultar recursos reales de una cuenta de AWS en modo de solo lectura.

## Estado

La Fase 7 está implementada. El servidor combina inventario uniforme, análisis conservador de actividad y diagnóstico explícito de salud y cobertura.

## Alcance previsto

- Transporte MCP local mediante `stdio`.
- Región principal: `eu-west-1`.
- Consultas de AWS exclusivamente de lectura y bajo mínimo privilegio.
- Tools disponibles: `health_check()`, `listar_recursos_aws()`, `analizar_actividad_recursos()` y `diagnosticar_cobertura_aws()`.
- Tool prevista: `revisar_free_tier()`.
- Sin Cost Explorer, despliegue en AWS ni CD.

## Desarrollo

El proyecto se gestiona con `uv` y Python 3.12 o posterior.

### Instalar dependencias

```powershell
uv sync
```

### Ejecutar el servidor

```powershell
uv run aws-resource-mcp
```

Para diagnóstico también puede ejecutarse como módulo:

```powershell
uv run python -m aws_resource_mcp.server
```

El servidor utiliza `stdio`: espera que un cliente MCP intercambie mensajes por la entrada y salida estándar. Puede abrirse con MCP Inspector mediante las herramientas incluidas en el SDK:

```powershell
uv run mcp dev src/aws_resource_mcp/server.py
```

### Ejecutar los tests

```powershell
uv run pytest
```

### Ejecutar el inventario AWS

Antes del diagnóstico real, comprueba qué identidad resolverá la configuración local:

```powershell
aws sts get-caller-identity
```

Después, ejecuta el inventario en la región predeterminada `eu-west-1`:

```powershell
uv run python -m aws_resource_mcp.aws.inventory
```

La región y el perfil compartido son opcionales:

```powershell
uv run python -m aws_resource_mcp.aws.inventory --region eu-central-1 --profile example
```

No se guardan claves en el proyecto. Boto3 usa su cadena estándar de resolución de credenciales; si se indica `AWS_PROFILE` o `--profile`, solo se selecciona un perfil que ya debe existir fuera del repositorio.

## Tools MCP

### `health_check`

`health_check(check_aws=True)` separa la salud local de la accesibilidad de AWS. Sin argumentos realiza como máximo una llamada protegida a STS; con `check_aws=false` no usa red. Devuelve versión, transporte, tools y adaptadores registrados, región, política económica y cero operaciones facturables. Sus estados son:

- `ok`: servidor y configuración válidos; STS respondió cuando se solicitó.
- `degraded`: el servidor funciona, pero faltan credenciales o STS no es accesible.
- `error`: la configuración segura o los registros internos no pueden inicializarse.

La identidad se anonimiza: solo se conserva el tipo general de principal y, cuando existe, una cuenta enmascarada. No ejecuta inventario, Resource Explorer, adaptadores, CloudTrail ni CloudWatch.

### `listar_recursos_aws`

Consulta el inventario AWS disponible para las credenciales locales sin modificar recursos. Parámetros:

- `region`: limita la búsqueda a una región; sin valor utiliza toda la cobertura disponible.
- `services`: filtra por servicios como `lambda`, `s3`, `ec2` o `rds`.
- `include_account_id`: permite omitir el ID de cuenta de la respuesta para facilitar su anonimización.
- `resource_types`: filtra por tipos dinámicos como `ec2:instance`.
- `query`: busca por texto o nombre.
- `all_regions`: utiliza las regiones habilitadas cuando no se especifica `region`.
- `include_details`: incluye metadatos específicos dentro de `details`.
- `include_cost_indicators`: incluye señales potenciales de coste sin afirmar gasto real.
- `confirm_potentially_billable_operations`: confirma operaciones potencialmente facturables; solo tiene efecto junto a `AWS_MCP_COST_MODE=allow-paid-with-confirmation`.
- `include_activity_summary`: añade un resumen breve usando solo campos ya obtenidos; no consulta CloudTrail ni CloudWatch.

Ejemplo de argumentos enviados por un cliente MCP:

```json
{
  "region": "eu-west-1",
  "services": ["lambda", "s3"],
  "include_account_id": false,
  "all_regions": true
}
```

Una respuesta `ok` cubre los tipos soportados por un índice agregador accesible; `partial` conserva resultados cuando faltan regiones, índices, vistas o permisos; `error` representa un problema global o parámetros inválidos. `coverage` explica qué pudo consultarse.

`resources`, `all_resources` y `resources_by_service` representan el mismo inventario deduplicado. Cada recurso contiene `id`, `arn`, `name`, `service`, `resource_type`, `region`, `account_id`, `state`, `created_at`, `sources`, `details`, `cost_indicators` y `activity`. La tool no calcula costes, no consulta Free Tier y no realiza operaciones de escritura.

### `analizar_actividad_recursos`

Analiza el último indicio conocido mediante el mismo registro y modelo para todos los recursos. Acepta filtros por `services`, `regions` y `resource_ids`, además de `inactive_days`, `lookback_days`, `include_administrative_events` y límites configurables. El historial de CloudTrail se limita a 90 días y se consulta por región, no una vez por recurso.

La respuesta separa `last_functional_usage_at`, `last_administrative_activity_at`, `last_configuration_change_at` y `last_state_change_at`. `best_known_activity_at` siempre indica también el tipo de señal. Un estado activo, una consulta `Describe*` o una fecha de modificación no se presentan como uso funcional.

Los estados por recurso son `active`, `inactive_candidate`, `unknown`, `not_supported` o `error`. Un candidato inactivo es únicamente un elemento para revisar: requiere antigüedad suficiente, una fuente relevante consultada y ausencia de evidencia reciente contradictoria. Falta de permisos, fuentes insuficientes o relaciones ambiguas producen `unknown`, no una falsa certeza de inactividad.

CloudWatch podría aportar métricas funcionales, pero `GetMetricData`, `GetMetricStatistics` y `ListMetrics` están registrados como potencialmente facturables y bloqueados. `include_paid_sources=true` solo solicita la explicación estructurada; no constituye consentimiento y nunca ejecuta esas operaciones en esta fase.

### `diagnosticar_cobertura_aws`

Explica qué puede consultar realmente el MCP sin enumerar recursos. Acepta filtros `services` y `regions`, y permite omitir las secciones de permisos, actividad o política económica.

Comprueba STS, regiones habilitadas, índices existentes de Resource Explorer, registro y capacidades de adaptadores, fuentes gratuitas de actividad y operaciones bloqueadas. Las comprobaciones se limitan a cinco regiones por ejecución, una muestra de CloudTrail y ninguna llamada de CloudWatch.

Los estados de cobertura distinguen `available`, `partial`, `unavailable`, `not_configured`, `permission_denied`, `blocked_by_cost_policy`, `not_supported`, `not_checked` y `error`. Una operación declarada como permitida por la política no se presenta como permiso IAM demostrado: el diagnóstico no ejecuta inventarios de servicio para probarlo.

Ejemplo:

```json
{
  "services": ["ec2", "rds"],
  "regions": ["eu-west-1"],
  "include_activity_sources": true
}
```

Las limitaciones indican impacto, si el MCP puede continuar, si faltan permisos, si resolverlas exigiría escritura y si podría existir coste. El diagnóstico nunca realiza la acción sugerida.

## Inventario AWS

Boto3 es el SDK oficial de AWS para Python. La capa de inventario utiliza:

- STS `GetCallerIdentity` para identificar la cuenta y la identidad efectiva.
- EC2 `DescribeRegions` para descubrir únicamente regiones habilitadas.
- Resource Explorer para descubrir dinámicamente recursos y tipos soportados mediante índices y vistas existentes.
- Un registro común de adaptadores para Lambda, S3, EC2/EBS/VPC, RDS/Aurora, DynamoDB, ECS/Fargate, API Gateway, CloudFormation, SQS, SNS, IAM, CloudFront y Route 53.
- CloudTrail `LookupEvents` para el historial regional gratuito de eventos de administración de los últimos 90 días.

Lambda y S3 fueron los primeros servicios implementados, pero ya no conservan rutas arquitectónicas especiales. Todos los adaptadores declaran metadatos, operaciones Boto3, alcance, tipos, detalles e indicadores mediante el mismo contrato. Los detalles particulares viven únicamente dentro de `details`.

Los resultados se deduplican por ARN o, si falta, por tipo, región e identificador/nombre. Se prefiere un índice agregador; con índices locales se combinan resultados y la cobertura es parcial. Si Resource Explorer no está disponible, se ejecutan todos los adaptadores seleccionados que soportan descubrimiento.

La ausencia de credenciales o la imposibilidad de identificar la cuenta es un error global para inventario, pero solo un estado `degraded` para la salud local. El diagnóstico conserva sus comprobaciones locales y omite de forma segura las dependientes de AWS.

Todas las llamadas Boto3 pasan primero por un registro central. Las operaciones no registradas, de escritura o de coste desconocido se bloquean. El modo predeterminado `AWS_MCP_COST_MODE=free-only` bloquea también operaciones potencialmente facturables. S3, SQS y SNS pertenecen a esta categoría porque AWS puede contabilizar sus peticiones; sus recursos todavía pueden aparecer mediante Resource Explorer.

Ejemplos para un cliente MCP: “¿Qué recursos hay en mi cuenta?”, “Lista las instancias EC2 de eu-west-1”, “Busca recursos llamados web” o “Muéstrame los tipos RDS desplegados”. Resource Explorer ofrece cobertura amplia, no universal.

## Documentación

- [Arquitectura](docs/architecture.md)
- [Decisiones](docs/decisions.md)
- [Fases](docs/phases.md)
- [Progreso](docs/progress.md)
- [Política zero-cost](docs/zero-cost-policy.md)
- [Adaptadores de servicios](docs/service-adapters.md)
- [Análisis de actividad](docs/activity-analysis.md)
- [Diagnóstico y cobertura](docs/diagnostics-and-coverage.md)
