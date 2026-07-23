# Flujo de consentimiento del inventario

El store efímero se reutiliza en la fase 8 mediante un tipo de consentimiento separado para Cost Explorer. No se mezclan scopes: un ID de inventario no autoriza costes y un ID económico no autoriza adaptadores. El flujo económico se documenta en [economic-analysis.md](economic-analysis.md).

## Problema

La política `free-only` bloqueaba correctamente operaciones que AWS puede contabilizar, pero la respuesta podía interpretarse como si S3, SQS o SNS estuvieran vacíos. El inventario ahora distingue entre «consultado y vacío» y «no consultado porque requiere consentimiento».

## Primera llamada

`listar_recursos_aws` ejecuta STS, regiones, adaptadores permitidos y Resource Explorer dentro de un presupuesto de tiempo. Devuelve inmediatamente los recursos disponibles. Las operaciones medibles quedan en `pending_operations` con servicio, operación, fase, propósito, alcance, regiones, máximo estimado de peticiones, posibilidad de paginación y `executed=false`.

Si existen pendientes, la respuesta usa `partial_pending_consent` y contiene una solicitud válida durante cinco minutos.

## Segunda llamada

El cliente reanuda la misma tool:

```json
{
  "consent_request_id": "<id>",
  "consent_action": "approve",
  "approved_services": ["s3"]
}
```

También puede cancelar con `consent_action: "cancel"`. Cancelar no ejecuta operaciones de inventario.

La aprobación:

- queda ligada mediante hash a la misma identidad AWS y al scope original;
- solo permite servicios seleccionados de la solicitud;
- se consume una vez;
- limita operaciones, regiones y peticiones;
- no habilita escritura ni operaciones desconocidas;
- no cambia la política global `free-only`.

El parámetro heredado `confirm_potentially_billable_operations` no concede acceso.

## Descubrimiento, enriquecimiento y paginación

Los adaptadores declaran por separado descubrimiento y enriquecimiento. Aprobar `s3:ListBuckets` no permite consultar versionado, lifecycle, replicación, logging, cifrado o public access block. Esas operaciones pueden originar una nueva solicitud.

La aprobación inicial permite la primera página prevista. Si aparece un token, el motor conserva solamente ese token y el inventario normalizado, marca `operation_truncated` y solicita una nueva aprobación. No pagina de forma ilimitada.

S3 solo enumera buckets; SQS solo enumera colas; SNS solo enumera topics. No se listan objetos, reciben mensajes, publican mensajes ni exponen endpoints de suscripción.

## Estado efímero

El proceso guarda en memoria:

- hash de identidad y scope;
- inventario provisional normalizado y sin account IDs;
- operaciones pendientes;
- tokens de continuación;
- expiración y estado de uso o cancelación.

No guarda respuestas Boto3 crudas, credenciales, access keys, secretos ni una identidad AWS legible. Reiniciar el servidor invalida las solicitudes.

La auditoría en memoria usa un hash corto del ID de consentimiento y registra únicamente timestamp, operaciones, regiones, peticiones, paginación y estado de consumo. No registra el ID completo, recursos, ARNs ni respuestas.

## Estados

- `complete_for_requested_scope`: no quedan fuentes pendientes dentro del scope.
- `partial_pending_consent`: hay recursos válidos y operaciones sin ejecutar.
- `partial_timeout`: terminó el presupuesto antes de completar servicios.
- `partial_permission_denied`: faltan permisos para parte del alcance.
- `partial_unavailable`: una fuente o servicio falló.
- `consent_cancelled`: el usuario canceló sin nuevas llamadas de inventario.
- `error`: entrada inválida o fallo global.

Los contadores separan operaciones potencialmente facturables únicas de peticiones SDK ejecutadas. Ambos son cero en la primera llamada.

## Uso desde Codex

Codex debe mostrar primero servicios, operaciones, regiones, límite y expiración de `consent_request`. Solo después de una confirmación explícita debe realizar la segunda llamada. Una autorización general en conversación no se reutiliza ni crea permiso persistente.

## Limitaciones

`potentially_billable` no demuestra que una petición concreta vaya a generar un cargo; indica que AWS la contabiliza y que el proyecto no puede garantizar coste cero dadas las condiciones acumuladas de la cuenta. El timeout se comprueba entre llamadas SDK y conserva resultados parciales; una llamada de red ya iniciada depende también de los timeouts del SDK.

## Comprobación manual anonimizada

El 2026-07-23, un cliente MCP nuevo por `stdio` validó el esquema y ejecutó únicamente la primera llamada en una región. Se conservaron 18 recursos de cuatro servicios y S3, SQS y SNS aparecieron como pendientes con `executed=false`. Operaciones potencialmente facturables únicas ejecutadas: 0. Peticiones potencialmente facturables ejecutadas: 0. No se usó el consentimiento generado.
