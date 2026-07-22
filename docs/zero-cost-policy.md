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

Esta política no determina gasto real, saldo de Free Tier ni elegibilidad. Tampoco usa Cost Explorer, Free Tier API, CloudWatch, CloudTrail, AWS Config ni estimaciones.

Referencias oficiales:

- [AWS Resource Explorer pricing](https://aws.amazon.com/resourceexplorer/pricing/)
- [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)
- [Amazon SQS pricing](https://aws.amazon.com/sqs/pricing/)
- [Amazon SNS pricing](https://aws.amazon.com/sns/pricing/)
