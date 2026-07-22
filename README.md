# AWS Resource MCP

Servidor MCP local, desarrollado en Python, para consultar recursos reales de una cuenta de AWS en modo de solo lectura.

## Estado

La Fase 4 está completada. El servidor MCP descubre recursos de forma uniforme mediante AWS Resource Explorer.

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

`resources`, `all_resources` y `resources_by_service` representan el mismo inventario deduplicado con un modelo común para todos los servicios. La tool no calcula costes, no consulta Free Tier y no realiza operaciones de escritura. `revisar_free_tier` se añadirá en una fase posterior.

## Inventario AWS

Boto3 es el SDK oficial de AWS para Python. La capa de inventario utiliza:

- STS `GetCallerIdentity` para identificar la cuenta y la identidad efectiva.
- EC2 `DescribeRegions` para descubrir únicamente regiones habilitadas.
- Resource Explorer para descubrir dinámicamente recursos y tipos soportados mediante índices y vistas existentes.
Los resultados se deduplican por ARN o, si falta, por tipo, región e identificador/nombre. Se prefiere un índice agregador; con índices locales se combinan resultados y la cobertura es parcial. El servidor nunca crea índices o vistas ni aplica rutas especiales según el servicio.

La ausencia de credenciales o la imposibilidad de identificar la cuenta es un error global. Los fallos posteriores son parciales: se conservan los datos disponibles y el problema aparece en `errors`.

Los permisos previstos incluyen `sts:GetCallerIdentity`, `ec2:DescribeRegions` y operaciones de lectura de Resource Explorer. La política IAM mínima se formalizará posteriormente.

Ejemplos para un cliente MCP: “¿Qué recursos hay en mi cuenta?”, “Lista las instancias EC2 de eu-west-1”, “Busca recursos llamados web” o “Muéstrame los tipos RDS desplegados”. Resource Explorer ofrece cobertura amplia, no universal.

## Documentación

- [Arquitectura](docs/architecture.md)
- [Decisiones](docs/decisions.md)
- [Fases](docs/phases.md)
- [Progreso](docs/progress.md)
