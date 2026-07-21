# Fases del proyecto

## Fase 0 — Preparación y documentación

Inicializar el proyecto Python con `uv`, crear la estructura mínima, documentar arquitectura, decisiones, progreso y plan.

## Fase 1 — MCP mínimo

Incorporar el SDK oficial de MCP para Python y exponer un servidor local mínimo mediante `stdio`, sin AWS.

## Fase 2 — Acceso a AWS mediante Boto3

Incorporar Boto3 y definir la capa de acceso de solo lectura a AWS, con `eu-west-1` como región principal.

## Fase 3 — Tool `listar_recursos_aws`

Implementar `listar_recursos_aws()` para consultar y devolver recursos AWS seleccionados en modo lectura.

## Fase 4 — Tool `revisar_free_tier`

Implementar `revisar_free_tier()` sin usar Cost Explorer.

## Fase 5 — Seguridad e IAM de solo lectura

Documentar y validar el modelo de mínimo privilegio, el uso seguro de credenciales externas y los límites de acceso.

## Fase 6 — Tests y calidad

Añadir pruebas automatizadas, lint y las comprobaciones de calidad necesarias.

## Fase 7 — Integración con cliente MCP

Documentar y verificar la ejecución local con un cliente MCP compatible.

## Fase 8 — GitHub Actions CI

Configurar CI para ejecutar lint y tests en cada pull request.

## Fase 9 — README, demo y cierre

Completar la documentación, preparar una demo reproducible y cerrar la primera versión del proyecto.
