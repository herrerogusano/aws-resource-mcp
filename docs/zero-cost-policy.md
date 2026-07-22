# Política zero-cost

## Valor predeterminado

```text
AWS_MCP_COST_MODE=free-only
```

Solo existen dos modos:

- `free-only`: permite operaciones registradas como gratuitas.
- `allow-paid-with-confirmation`: permite operaciones potencialmente facturables únicamente cuando la petición incluye confirmación explícita.

No existe un modo de ejecución facturable sin confirmación.

## Clasificaciones

- `free`: permitida.
- `potentially_billable`: bloqueada salvo modo y confirmación explícitos.
- `unknown`: bloqueada.
- `write`: bloqueada siempre.

El guard se ejecuta antes de cada llamada Boto3. Una operación bloqueada devuelve `cost_permission_required`, la operación y `executed=false`; el método del cliente no se ejecuta.

S3 cobra peticiones GET, LIST y otras peticiones; SQS contabiliza cada acción; SNS contabiliza operaciones de propietario y suscripción. Por eso sus operaciones directas se clasifican como potencialmente facturables. Resource Explorer está disponible sin coste adicional para búsquedas básicas, aunque AWS advierte que llamadas a otros servicios pueden generar cargos.

Esta política no determina gasto real, saldo de Free Tier ni elegibilidad. Tampoco usa Cost Explorer, Free Tier API, AWS Config ni estimaciones.

## Actividad en la Fase 6

`cloudtrail:LookupEvents` está registrado como lectura gratuita y permitido en `free-only`. AWS ofrece Event History sin cargo para consultar los eventos de administración de los últimos 90 días; no se crea ningún trail ni event data store.

Las operaciones `cloudwatch:GetMetricData`, `cloudwatch:GetMetricStatistics` y `cloudwatch:ListMetrics` se registran como `potentially_billable` y permanecen bloqueadas. La respuesta incluye `executed=false`, `consent_required=true` y el propósito del enriquecimiento. `include_paid_sources=true` no cambia el guard ni ejecuta una llamada.

No se usan Metrics Insights, Logs Insights, métricas personalizadas, CloudTrail Lake, data stores, SQL ni archivos de trails en S3.

Referencias oficiales:

- [AWS Resource Explorer pricing](https://aws.amazon.com/resourceexplorer/pricing/)
- [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)
- [Amazon SQS pricing](https://aws.amazon.com/sqs/pricing/)
- [Amazon SNS pricing](https://aws.amazon.com/sns/pricing/)
- [AWS CloudTrail Event History](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html)
- [AWS CloudTrail pricing](https://aws.amazon.com/cloudtrail/pricing/)
- [Amazon CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/)
