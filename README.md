# AWS Resource MCP

Servidor MCP local, desarrollado en Python, para consultar recursos reales de una cuenta de AWS en modo de solo lectura.

## Estado

La Fase 5 está completada. El servidor combina Resource Explorer con un registro uniforme de adaptadores de solo lectura para los principales servicios AWS.

## Alcance previsto

- Transporte MCP local mediante `stdio`.
- Región principal: `eu-west-1`.
- Consultas de AWS exclusivamente de lectura y bajo mínimo privilegio.
- Tools previstas: `listar_recursos_aws()` y `revisar_free_tier()`.
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

`health_check()` no recibe parámetros ni usa red, credenciales o AWS. Devuelve una respuesta estable con el estado del servidor, su nombre y un mensaje de diagnóstico.

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

## Inventario AWS

Boto3 es el SDK oficial de AWS para Python. La capa de inventario utiliza:

- STS `GetCallerIdentity` para identificar la cuenta y la identidad efectiva.
- EC2 `DescribeRegions` para descubrir únicamente regiones habilitadas.
- Resource Explorer para descubrir dinámicamente recursos y tipos soportados mediante índices y vistas existentes.
- Un registro común de adaptadores para Lambda, S3, EC2/EBS/VPC, RDS/Aurora, DynamoDB, ECS/Fargate, API Gateway, CloudFormation, SQS, SNS, IAM, CloudFront y Route 53.

Lambda y S3 fueron los primeros servicios implementados, pero ya no conservan rutas arquitectónicas especiales. Todos los adaptadores declaran metadatos, operaciones Boto3, alcance, tipos, detalles e indicadores mediante el mismo contrato. Los detalles particulares viven únicamente dentro de `details`.

Los resultados se deduplican por ARN o, si falta, por tipo, región e identificador/nombre. Se prefiere un índice agregador; con índices locales se combinan resultados y la cobertura es parcial. Si Resource Explorer no está disponible, se ejecutan todos los adaptadores seleccionados que soportan descubrimiento.

La ausencia de credenciales o la imposibilidad de identificar la cuenta es un error global. Los fallos posteriores son parciales: se conservan los datos disponibles y el problema aparece en `errors`.

Todas las llamadas Boto3 pasan primero por un registro central. Las operaciones no registradas, de escritura o de coste desconocido se bloquean. El modo predeterminado `AWS_MCP_COST_MODE=free-only` bloquea también operaciones potencialmente facturables. S3, SQS y SNS pertenecen a esta categoría porque AWS puede contabilizar sus peticiones; sus recursos todavía pueden aparecer mediante Resource Explorer.

Ejemplos para un cliente MCP: “¿Qué recursos hay en mi cuenta?”, “Lista las instancias EC2 de eu-west-1”, “Busca recursos llamados web” o “Muéstrame los tipos RDS desplegados”. Resource Explorer ofrece cobertura amplia, no universal.

## Documentación

- [Arquitectura](docs/architecture.md)
- [Decisiones](docs/decisions.md)
- [Fases](docs/phases.md)
- [Progreso](docs/progress.md)
- [Política zero-cost](docs/zero-cost-policy.md)
- [Adaptadores de servicios](docs/service-adapters.md)
