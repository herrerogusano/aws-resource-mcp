# Fases del proyecto

## Fase 0 — Preparación y documentación

Inicializar el proyecto Python con `uv`, crear la estructura mínima, documentar arquitectura, decisiones, progreso y plan.

## Fase 1 — MCP mínimo

Incorporar el SDK oficial de MCP para Python y exponer un servidor local mínimo mediante `stdio`, sin AWS.

## Fase 2 — Acceso a AWS mediante Boto3

Incorporar Boto3 y definir la capa de acceso de solo lectura a AWS, con `eu-west-1` como región principal.

## Fase 3 — Tool `listar_recursos_aws`

Implementar `listar_recursos_aws()` para consultar y devolver recursos AWS seleccionados en modo lectura.

## Fase 4 — Descubrimiento general con Resource Explorer

Ampliar el inventario a múltiples servicios y regiones con cobertura explícita, normalización y deduplicación uniformes.

## Fase 5 — Adaptadores y detalles con interfaz común

Implementar el registro común, adaptadores de solo lectura, detalles normalizados, indicadores potenciales, fallback uniforme y política zero-cost. La actividad queda marcada como no analizada.

## Fase 6 — Actividad y último uso conocido

Analizar señales de actividad mediante un contrato común, distinguiendo evidencia, ausencia de datos y fecha de último uso.

## Fase 7 — Tool `revisar_free_tier`

Implementar `revisar_free_tier()` sin usar Cost Explorer.

## Fase 8 — Seguridad e IAM de solo lectura

Documentar y validar el modelo de mínimo privilegio, el uso seguro de credenciales externas y los límites de acceso.

## Fase 9 — Tests y calidad

Añadir pruebas automatizadas, lint y las comprobaciones de calidad necesarias.

## Fase 10 — Integración con cliente MCP

Documentar y verificar la ejecución local con un cliente MCP compatible.

## Fase 11 — GitHub Actions CI

Configurar CI para ejecutar lint y tests en cada pull request.

## Fase 12 — README, demo y cierre

Completar la documentación, preparar una demo reproducible y cerrar la primera versión del proyecto.
