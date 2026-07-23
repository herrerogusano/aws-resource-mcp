# Análisis económico

## Alcance

La fase 8 separa tres preguntas que no son equivalentes:

1. `analizar_riesgo_costes`: ¿qué recursos presentan señales que merecen revisión?
2. `revisar_free_tier`: ¿qué uso y límites comunica oficialmente AWS Free Tier?
3. `consultar_costes_aws`: ¿qué gasto real agregado comunica Cost Explorer para un periodo exacto?

Una señal potencial nunca se presenta como gasto confirmado. Estar dentro de Free Tier no prueba que un recurso concreto sea gratuito. Un coste agregado tampoco demuestra por sí solo qué recurso lo originó.

## Modelo económico común

Cada recurso analizado conserva el recurso normalizado y una sección `economics` idéntica:

```json
{
  "risk_level": "high",
  "priority_score": 70,
  "indicators": [],
  "activity_status": "unknown",
  "actual_cost_status": "not_checked",
  "actual_cost": null,
  "free_tier_status": "unknown",
  "evidence": [],
  "limitations": [],
  "recommendations": []
}
```

Niveles de riesgo:

- `none_detected`: no se detectó una señal potencial; no significa coste cero.
- `low`, `medium`, `high`, `critical`: prioridad creciente para revisión.
- `unknown`: no hay datos suficientes para clasificar.

Estados de coste real:

- `confirmed`, `zero_reported`, `not_checked`, `pending_consent`;
- `blocked_by_cost_policy`, `unavailable`, `permission_denied`;
- `truncated`, `error`.

Estados Free Tier:

- `within_limit`, `approaching_limit`, `limit_exceeded`;
- `credit_available`, `credit_exhausted`;
- `not_eligible`, `not_applicable`, `unknown`;
- `unavailable`, `permission_denied`, `error`.

## Priorización transparente

El motor reutiliza `cost_indicators` del inventario y, opcionalmente, la salida del pipeline común de actividad. La puntuación parte de la señal de mayor severidad: baja 20, media 45 y alta 70. Añade hasta 15 puntos por varias señales y 15 cuando una señal de coste coexiste con `inactive_candidate`. El resultado se limita a 100.

La actividad `unknown` no se penaliza como inactividad. Las recomendaciones son informativas; el MCP no detiene, modifica ni elimina recursos.

`include_actual_cost=true` no consulta Cost Explorer. Solo adjunta una solicitud de consentimiento separada.

## AWS Free Tier

`revisar_free_tier` utiliza:

- `freetier:GetFreeTierUsage`;
- `freetier:GetAccountPlanState`.

AWS documenta el acceso programático a estos datos sin coste. Ambas operaciones se registran como `free`, de lectura y habilitadas en `free-only`. El endpoint de la API se utiliza en `us-east-1`; las ofertas devueltas pueden referirse a regiones concretas o a `global`.

La primera página es el límite predeterminado. `max_pages` puede ampliarse explícitamente hasta cinco. La respuesta informa páginas consultadas, truncamiento, operaciones y cero operaciones facturables.

Limitaciones:

- el uso puede estar estimado y actualizarse solo varias veces al día;
- una oferta puede dejar de aparecer al agotarse;
- la elegibilidad y los créditos dependen de la cuenta;
- una oferta ausente no prueba coste;
- no se consulta gasto facturado.

## Cost Explorer y consentimiento

`ce:GetCostAndUsage` se clasifica como `potentially_billable`. AWS publica un precio de 0,01 USD por petición sobre la vista de facturación principal. No se usan vistas personalizadas.

La primera llamada a `consultar_costes_aws`:

- no crea una sesión Boto3;
- no llama a STS;
- no llama a Cost Explorer;
- devuelve periodo, granularidad, agrupación, filtros, operación, expiración, máximo de una petición y coste máximo estimado.

La segunda llamada debe repetir exactamente el scope y aportar:

```text
consent_request_id=<id efímero>
consent_action=approve
```

La aprobación:

- obtiene la identidad mediante STS y vincula el grant a esa ejecución;
- consume el grant antes de llamar a Cost Explorer;
- autoriza únicamente `GetCostAndUsage`;
- permite una sola petición y una sola página;
- destruye scope, resultado provisional y token al terminar;
- conserva solo un tombstone y auditoría anonimizada para impedir reutilización.

Si existe otra página, el token no se expone y se crea una solicitud nueva. Cancelar destruye el estado sin llamar a AWS.

Las fechas siguen la semántica de Cost Explorer: `end_date` es exclusiva. Se admite granularidad mensual o diaria y agrupación opcional por servicio. El periodo máximo es 366 días. Forecast y detalle por recurso son operaciones separadas y no están implementados en esta fase; solicitarlos nunca amplía silenciosamente un consentimiento.

## Privacidad

No se devuelven ni guardan:

- identidad o ID de cuenta legibles;
- ARN de billing view;
- linked accounts;
- métodos de pago, impuestos o direcciones;
- credenciales;
- respuestas Boto3 completas;
- tokens de paginación.

Los resultados de Cost Explorer se reducen a periodos, servicio opcional, importe, moneda y marca de estimación.

## Preguntas admitidas

- “¿Qué recursos parecen tener mayor riesgo de coste?”
- “¿Qué recursos potencialmente caros parecen inactivos?”
- “¿Estoy cerca de algún límite Free Tier?”
- “¿Mi plan tiene créditos disponibles?”
- “Prepara una consulta del gasto de este mes.”
- “Tras confirmar la solicitud exacta, consulta el coste agregado por servicio.”

## Fuentes oficiales verificadas

- [AWS Free Tier usage API at no cost](https://aws.amazon.com/about-aws/whats-new/2023/11/aws-free-tier-usage-getfreetierusage-api/)
- [Tracking Free Tier usage and account plan](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/tracking-free-tier-usage.html)
- [Free Tier API usage](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-free-tier-api.html)
- [Cost Explorer API pricing](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/)
- [GetCostAndUsage API](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html)

