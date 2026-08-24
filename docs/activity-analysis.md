# Análisis de actividad

La fase 8 puede reutilizar este resultado para priorizar señales potenciales de coste. `inactive_candidate` aumenta la prioridad únicamente cuando ya existe un indicador económico; `unknown` nunca se interpreta como inactividad ni como gasto.

## Qué significa actividad

La tool `analizar_actividad_recursos` no reduce toda la evidencia a un ambiguo `last_used_at`. Usa cinco tipos comunes:

| Tipo | Significado | Ejemplo | Prueba uso funcional |
|---|---|---|---|
| `functional_usage` | El recurso realizó su función | `Invoke`, `RoleLastUsed` | Sí, si la relación es directa |
| `administrative_activity` | Se ejecutó una llamada de gestión | `DescribeInstances` | No |
| `configuration_change` | Se creó o modificó configuración | `UpdateFunctionConfiguration` | No |
| `resource_state` | Estado o transición indirecta | instancia iniciada o disponible | No |
| `unknown` | No existe evidencia suficiente | evento sin recurso relacionado | No |

Por eso el modelo mantiene `last_functional_usage_at`, `last_administrative_activity_at`, `last_configuration_change_at` y `last_state_change_at`. `best_known_activity_at` identifica la evidencia más reciente, pero `best_known_activity_type` conserva su significado.

## Modelo común

Todos los servicios devuelven la misma forma:

```json
{
  "status": "active",
  "last_activity_at": "2026-07-15T10:30:00Z",
  "days_since_activity": 7,
  "activity_type": "administrative_activity",
  "activity_name": "UpdateFunctionConfiguration",
  "source": "cloudtrail_event_history",
  "confidence": "medium",
  "lookback_days": 90,
  "last_functional_usage_at": null,
  "last_administrative_activity_at": "2026-07-15T10:30:00Z",
  "last_configuration_change_at": null,
  "last_state_change_at": null,
  "best_known_activity_at": "2026-07-15T10:30:00Z",
  "best_known_activity_type": "administrative_activity",
  "evidence": [],
  "limitations": [],
  "paid_data_available": true,
  "paid_data_requested": false,
  "paid_data_executed": false
}
```

Estados: `active`, `inactive_candidate`, `unknown`, `not_supported`, `blocked_by_cost_policy` y `error`. Confianza: `high`, `medium`, `low` y `unknown`.

## CloudTrail Event History

`cloudtrail:LookupEvents` es la fuente transversal principal. AWS ofrece Event History sin cargo, habilitado por defecto y separado de trails y event data stores. Cubre hasta 90 días de eventos de administración en cada región.

La implementación:

- limita `lookback_days` a 90;
- pagina con un máximo de 50 resultados por llamada;
- acepta como máximo un atributo de búsqueda;
- consulta una vez por región y reutiliza los eventos entre recursos;
- solo relaciona eventos que incluyan identificadores compatibles;
- devuelve resultados parciales por región;
- no crea trails, event data stores ni consultas Lake.

La evidencia normalizada excluye identidad completa, IP de origen, access key ID, user agent, parámetros y el JSON completo del evento. Solo conserva fecha, nombre, origen, lectura/escritura, región, identificadores relacionados, tipo y confianza.

Event History no muestra eventos de datos. Por tanto, no permite prometer el último `GetObject` de S3, ni todas las invocaciones Lambda, peticiones API o accesos a datos. Un evento administrativo reciente es actividad, pero no prueba uso funcional.

## Confianza y candidatos inactivos

- Alta: señal funcional específica o campo oficial de último uso.
- Media: evento administrativo directamente relacionado, cambio de configuración o transición de estado.
- Baja: creación, modificación general o estado indirecto.
- Desconocida: ausencia de evidencia, permiso insuficiente, relación ambigua o fuente bloqueada.

`inactive_candidate` requiere un recurso suficientemente antiguo, una fuente relevante consultada, evidencia fuera del umbral y ausencia de evidencia reciente contradictoria. Es una invitación a revisar, nunca una afirmación de abandono.

Se devuelve `unknown` si el recurso es reciente, faltan permisos, no existe una fuente compatible, la relación CloudTrail es ambigua o la única fuente necesaria está bloqueada. Un recurso encendido, disponible o asociado no se considera usado automáticamente.

## Fuentes por servicio y limitaciones

- Lambda: `LastModified`, estado y eventos de administración; `LastModified` no es última invocación.
- S3: creación/configuración y eventos administrativos disponibles; no se listan objetos ni se conoce el último acceso sin data events o métricas.
- EC2/EBS: lanzamiento/creación, estado y eventos de inicio, parada, reinicio, asociación o configuración; no se infiere tráfico ni I/O.
- RDS/Aurora: creación, estado y eventos administrativos; no se abre una conexión ni se afirman conexiones recientes.
- DynamoDB: creación, estado y cambios administrativos; no se ejecutan `Scan` ni `Query`.
- ECS/Fargate: tareas, servicios, estado y despliegues disponibles; tareas activas no prueban tráfico.
- API Gateway: creación, stages y cambios administrativos; no se invoca la API.
- SQS/SNS: creación/configuración y eventos administrativos; no se reciben ni publican mensajes.
- CloudFormation: creación, última actualización, estado y eventos administrativos.
- IAM: `RoleLastUsed` y fechas oficiales disponibles, sin leer ni exponer claves.
- CloudFront/Route 53: modificación, estado y eventos administrativos; no se consultan logs.

Todos atraviesan `get_free_activity_signals`, el registro común, el mismo clasificador y el mismo constructor de resultados.

## CloudWatch bloqueado

Las métricas de CloudWatch podrían responder mejor preguntas sobre invocaciones, conexiones, tráfico, solicitudes o mensajes. `GetMetricData`, `GetMetricStatistics` y `ListMetrics` pueden generar cargos y están registradas como `potentially_billable`.

En esta fase siempre se devuelve una explicación con `executed=false` y `requires_explicit_confirmation=true`. `include_paid_sources=true` no concede consentimiento. No se usan Metrics Insights, Logs Insights ni métricas personalizadas.

Una futura autorización deberá limitar operación, recursos, periodo, máximo de consultas y una única ejecución.

## Relación con el diagnóstico

`diagnosticar_cobertura_aws` no analiza recursos. Informa de qué adaptadores declaran señales gratuitas, prueba `cloudtrail:LookupEvents` con una única muestra en una región comprobada y describe CloudWatch como `blocked_by_cost_policy`. Un permiso denegado en CloudTrail no borra la cobertura de STS, regiones, Resource Explorer o adaptadores.

## Límites de ejecución

Los valores predeterminados son 100 recursos, 5 regiones, 20 evidencias por recurso, 500 eventos CloudTrail totales y 30 segundos. La concurrencia está limitada a una consulta secuencial, los datos solo se almacenan en memoria durante la ejecución y cualquier límite o fallo produce resultados parciales sin borrar los demás.

## Preguntas compatibles

- ¿Cuándo se utilizó por última vez esta Lambda?
- ¿Qué recursos no muestran actividad desde hace 30 días?
- ¿Qué EC2 parecen inactivas?
- ¿Cuál es el último evento conocido de esta base RDS?
- Muéstrame los recursos potencialmente abandonados.
- ¿Qué recursos no tienen suficientes datos para saber si se usan?

La respuesta puede ser `unknown`; esa incertidumbre es parte deliberada del modelo.

## Referencias oficiales

- [Working with CloudTrail Event History](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html)
- [CloudTrail LookupEvents](https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_LookupEvents.html)
- [AWS CloudTrail pricing](https://aws.amazon.com/cloudtrail/pricing/)
- [Amazon CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/)
## Permisos IAM

Las señales gratuitas de los adaptadores y `cloudtrail:LookupEvents` aparecen
en la política `free-only`. CloudWatch permanece excluido: ni una política IAM
generada ni `include_paid_sources=true` autorizan métricas. Cualquier futura
incorporación deberá verificar coste, sensibilidad y consentimiento antes de
entrar en una política.
