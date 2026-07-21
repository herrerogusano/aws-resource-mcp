# AWS Resource MCP

Servidor MCP local, desarrollado en Python, para consultar recursos reales de una cuenta de AWS en modo de solo lectura.

## Estado

La Fase 2 está completada. El proyecto incluye un servidor MCP mínimo y una capa Python independiente que consulta un inventario AWS de solo lectura mediante Boto3. El inventario todavía no está expuesto como tool MCP.

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

## Tool `health_check`

`health_check()` no recibe parámetros ni usa red, credenciales o AWS. Devuelve una respuesta estable con el estado del servidor, su nombre y un mensaje de diagnóstico.

El servidor MCP continúa exponiendo únicamente `health_check`. La capa AWS se integrará con MCP en la Fase 3.

## Inventario AWS

Boto3 es el SDK oficial de AWS para Python. La capa de inventario utiliza:

- STS `GetCallerIdentity` para identificar la cuenta y la identidad efectiva.
- Lambda `ListFunctions`, mediante paginador, para obtener metadatos de funciones sin descargar código, leer variables ni invocarlas.
- S3 `ListAllMyBuckets` y `GetBucketLocation` para obtener nombres, fechas de creación y regiones, sin listar objetos ni contenido.

La ausencia de credenciales o la imposibilidad de identificar la cuenta es un error global. Un fallo de Lambda, S3 o de la región de un bucket es parcial: se conservan los demás datos y el problema aparece en `errors`.

Los permisos de lectura previstos son `sts:GetCallerIdentity`, `lambda:ListFunctions`, `s3:ListAllMyBuckets` y `s3:GetBucketLocation`. La política IAM mínima se formalizará en la Fase 5.

## Documentación

- [Arquitectura](docs/architecture.md)
- [Decisiones](docs/decisions.md)
- [Fases](docs/phases.md)
- [Progreso](docs/progress.md)
