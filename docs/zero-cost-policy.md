# Política zero-cost

## Valor predeterminado

```text
AWS_MCP_COST_MODE=free-only
```

La configuración conserva dos valores por compatibilidad:

- `free-only`: permite operaciones registradas como gratuitas.
- `allow-paid-with-confirmation`: valor heredado; ya no concede por sí mismo operaciones potencialmente facturables.

No existe un modo de ejecución facturable sin confirmación.

## Clasificaciones

- `free`: permitida.
- `potentially_billable`: bloqueada salvo autorización efímera exacta.
- `unknown`: bloqueada.
- `write`: bloqueada siempre.

El guard se ejecuta antes de cada llamada Boto3. Una operación bloqueada devuelve `cost_permission_required`, la operación y `executed=false`; el método del cliente no se ejecuta. El antiguo booleano de confirmación no abre el guard.

S3 cobra peticiones GET, LIST y otras peticiones; SQS contabiliza cada acción; SNS contabiliza operaciones de propietario y suscripción. Por eso sus operaciones directas se clasifican como potencialmente facturables. Resource Explorer está disponible sin coste adicional para búsquedas básicas, aunque AWS advierte que llamadas a otros servicios pueden generar cargos.

Esta política no convierte señales en gasto real ni garantiza elegibilidad. Free Tier se consulta únicamente mediante operaciones documentadas sin coste. Cost Explorer permanece bloqueado hasta recibir un grant exacto.

## Actividad en la Fase 6

`cloudtrail:LookupEvents` está registrado como lectura gratuita y permitido en `free-only`. AWS ofrece Event History sin cargo para consultar los eventos de administración de los últimos 90 días; no se crea ningún trail ni event data store.

Las operaciones `cloudwatch:GetMetricData`, `cloudwatch:GetMetricStatistics` y `cloudwatch:ListMetrics` se registran como `potentially_billable` y permanecen bloqueadas. La respuesta incluye `executed=false`, `consent_required=true` y el propósito del enriquecimiento. `include_paid_sources=true` no cambia el guard ni ejecuta una llamada.

No se usan Metrics Insights, Logs Insights, métricas personalizadas, CloudTrail Lake, data stores, SQL ni archivos de trails en S3.

## Diagnóstico en la Fase 7

`health_check` solo puede ejecutar `sts:GetCallerIdentity`. `diagnosticar_cobertura_aws` reutiliza operaciones gratuitas registradas para STS, `ec2:DescribeRegions`, metadatos de Resource Explorer y una única muestra `cloudtrail:LookupEvents`.

El diagnóstico no ejecuta adaptadores de inventario para probar permisos. Informa por separado de que una operación está registrada y permitida por la política, pero su permiso IAM queda `not_checked`. Las operaciones S3, SQS, SNS y CloudWatch continúan bloqueadas cuando corresponda. El contador `billable_operations_executed` es cero por defecto y en la comprobación manual.

## Inventario con consentimiento

`ListBuckets`, `ListQueues` y `ListTopics` permanecen clasificadas como `potentially_billable`. La primera llamada no las ejecuta: devuelve propósito, regiones, máximo estimado de peticiones, expiración y `executed=false`.

Una aprobación crea un grant de una sola ejecución. No autoriza automáticamente detalles, otras regiones ni páginas adicionales. Si AWS devuelve un token, el resultado se marca truncado y una continuación exige consentimiento nuevo. Se cuentan tanto las operaciones únicas como las peticiones SDK reales.

La política no garantiza coste cero: garantiza que las operaciones medibles no se ejecutan sin consentimiento explícito y acotado. Nunca se listan objetos, reciben mensajes ni publican contenidos.

## Economía en la Fase 8

Operaciones gratuitas:

| Operación | Acceso | Clasificación | `free-only` |
|---|---|---|---|
| `freetier:GetFreeTierUsage` | read | free | habilitada |
| `freetier:GetAccountPlanState` | read | free | habilitada |

AWS documenta el acceso programático a Free Tier y al estado del plan sin coste. La evidencia se verificó el 2026-07-23. Estas llamadas no consultan facturas ni prueban que un recurso sea gratuito.

Operaciones potencialmente facturables:

| Operación | Estado en esta fase |
|---|---|
| `ce:GetCostAndUsage` | implementada solo con consentimiento exacto |
| `ce:GetCostForecast` | registrada y bloqueada; no implementada |
| `ce:GetCostAndUsageWithResources` | registrada y bloqueada; no implementada |

AWS publica 0,01 USD por petición de la API Cost Explorer sobre la vista principal. La primera llamada de `consultar_costes_aws` ejecuta cero llamadas AWS y muestra un máximo de una petición y 0,01 USD. La aprobación no cambia el modo global, no persiste, no autoriza otra página y no usa billing views personalizadas.

Los dos contadores permanecen separados:

- `potentially_billable_operations_executed`: tipos de operación potencialmente facturable realmente ejecutados;
- `billable_operations_executed`: peticiones SDK realizadas bajo consentimiento.

Por defecto ambos son cero. En una aprobación válida de una página de Cost Explorer ambos reflejan una única petición `GetCostAndUsage`.

Referencias oficiales:

- [AWS Resource Explorer pricing](https://aws.amazon.com/resourceexplorer/pricing/)
- [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)
- [Amazon SQS pricing](https://aws.amazon.com/sqs/pricing/)
- [Amazon SNS pricing](https://aws.amazon.com/sns/pricing/)
- [AWS CloudTrail Event History](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html)
- [AWS CloudTrail pricing](https://aws.amazon.com/cloudtrail/pricing/)
- [Amazon CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/)
- [AWS Free Tier API at no cost](https://aws.amazon.com/about-aws/whats-new/2023/11/aws-free-tier-usage-getfreetierusage-api/)
- [Tracking AWS Free Tier usage](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/tracking-free-tier-usage.html)
- [AWS Cost Explorer pricing](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/)
## Relación con IAM

La política `free-only` contiene únicamente operaciones clasificadas como
gratuitas. La política `consented-readonly` puede habilitar técnicamente
operaciones contabilizables, pero no cambia el modo económico ni omite el
consentimiento efímero. Operaciones con coste desconocido no entran en ninguna
política de ejecución.
