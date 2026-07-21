# Arquitectura

## Visión inicial

El proyecto será un servidor MCP local escrito en Python. Un cliente MCP lo iniciará como proceso local y se comunicará con él mediante transporte `stdio`.

En fases posteriores, el servidor usará el SDK oficial de MCP para Python y Boto3 para realizar consultas de solo lectura contra AWS. La región principal será `eu-west-1`.

```text
Cliente MCP <-> stdio <-> servidor AWS Resource MCP <-> Boto3 <-> AWS
```

## Límites de esta fase

No se implementan todavía el servidor MCP, las tools, Boto3, el SDK MCP, credenciales ni llamadas a AWS.

## Principios

- Ejecución local: no hay despliegue en AWS.
- Solo lectura y mínimo privilegio para cualquier acceso futuro a AWS.
- Configuración de credenciales fuera del repositorio.
- Sin uso de Cost Explorer.
