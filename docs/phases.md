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

Completada. Analiza señales gratuitas mediante el contrato común de adaptadores y CloudTrail Event History, separa uso funcional, actividad administrativa, cambios de configuración y estado, y bloquea CloudWatch por la política zero-cost.

## Fase 7 — Diagnóstico, cobertura y health check avanzado

Implementada. Separa salud local y cobertura AWS, amplía `health_check` con STS opcional y añade `diagnosticar_cobertura_aws` para regiones, Resource Explorer, adaptadores, permisos, actividad y política zero-cost.

## Fase 7.5 — Finalización del inventario con consentimiento

Implementada. Devuelve primero el inventario gratuito y representa S3, SQS y SNS como pendientes cuando su enumeración puede contabilizar peticiones. Una segunda llamada puede conceder una autorización efímera, exacta, limitada y de un solo uso. Descubrimiento, enriquecimiento y paginación se autorizan por separado.

## Fase 8 — Riesgo económico, Free Tier y costes reales

Implementada. Añade un modelo económico uniforme, `analizar_riesgo_costes`, las consultas gratuitas `revisar_free_tier` y una integración mínima con Cost Explorer que exige consentimiento efímero, exacto y de una sola petición. La primera llamada de coste no contacta con AWS; forecast y detalle por recurso quedan separados y no implementados.

## Fase 9 — Seguridad e IAM de solo lectura

Implementada. Deriva permisos IAM desde el registro central, genera políticas
separadas para `free-only`, consentimiento y uso combinado, valida exclusiones
sensibles y documenta un rol dedicado con credenciales temporales. No modifica
IAM automáticamente.

## Fase 10 — Tests y calidad

Añadir pruebas automatizadas, lint y las comprobaciones de calidad necesarias.

## Fase 11 — Integración con cliente MCP

Documentar y verificar la ejecución local con un cliente MCP compatible.

## Fase 12 — GitHub Actions CI

Configurar CI para ejecutar lint y tests en cada pull request.

## Fase 13 — README, demo y cierre

Completar la documentación, preparar una demo reproducible y cerrar la primera versión del proyecto.
