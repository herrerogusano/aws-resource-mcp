# AWS Resource MCP

Servidor MCP local, desarrollado en Python, para consultar recursos reales de una cuenta de AWS en modo de solo lectura.

## Estado

El proyecto se encuentra en la Fase 0: preparación y documentación. Aún no incluye herramientas MCP, integración con AWS, Boto3 ni el SDK de MCP.

## Alcance previsto

- Transporte MCP local mediante `stdio`.
- Región principal: `eu-west-1`.
- Consultas de AWS exclusivamente de lectura y bajo mínimo privilegio.
- Tools previstas: `listar_recursos_aws()` y `revisar_free_tier()`.
- Sin Cost Explorer, despliegue en AWS ni CD.

## Desarrollo

El proyecto se gestiona con `uv` y Python 3.12 o posterior.

```powershell
uv sync
```

## Documentación

- [Arquitectura](docs/architecture.md)
- [Decisiones](docs/decisions.md)
- [Fases](docs/phases.md)
- [Progreso](docs/progress.md)
