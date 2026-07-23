# Decisiones

## D-001 — Python y uv

**Decisión:** usar Python 3.12 o posterior y `uv` para gestionar el proyecto y sus dependencias.

**Motivo:** ofrece un flujo de desarrollo moderno y reproducible para un proyecto Python local.

## D-002 — Ejecución local por stdio

**Decisión:** el servidor MCP se ejecutará localmente mediante transporte `stdio`.

**Motivo:** el servidor está diseñado para ejecutarse como proceso local y no necesita infraestructura remota.

## D-003 — AWS de solo lectura

**Decisión:** cualquier integración futura con AWS será exclusivamente de lectura y con permisos de mínimo privilegio.

**Motivo:** protege la cuenta y limita el alcance operativo del proyecto.

## D-004 — Alcance funcional previsto

**Decisión:** las tools objetivo serán `listar_recursos_aws()` y `revisar_free_tier()`; no se utilizará Cost Explorer.

**Motivo:** mantiene un alcance inicial pequeño, útil y fácil de validar.

## D-005 — Calidad sin CD

**Decisión:** habrá CI de GitHub con lint y tests en cada pull request, pero no CD ni despliegue en AWS.

**Motivo:** el proyecto es local y la automatización necesaria se limita a validar cambios.

## D-006 — SDK oficial de MCP y FastMCP

**Decisión:** usar el SDK oficial de MCP para Python y `FastMCP` para construir el servidor.

**Motivo:** FastMCP permite registrar tools a partir de funciones Python tipadas y documentadas, manteniendo pequeña la infraestructura del servidor.

## D-007 — MCP estable 1.x

**Decisión:** restringir temporalmente la dependencia a `mcp[cli]>=1.27,<2`.

**Motivo:** evita versiones preliminares y cambios incompatibles de una futura versión principal mientras el proyecto evoluciona.

## D-008 — Separación entre servidor y tools

**Decisión:** mantener la inicialización de FastMCP en `server.py` y la lógica de cada tool en módulos dentro de `tools/`.

**Motivo:** permite probar la lógica directamente, sin transporte, red ni un cliente MCP.

## D-009 — Boto3 y cadena estándar de credenciales

**Decisión:** usar Boto3 sin leer ni almacenar claves en el código. La configuración solo admite región y un nombre opcional de perfil.

**Motivo:** delega la resolución segura de credenciales en el mecanismo estándar del SDK y evita duplicar manejo sensible.

## D-010 — Capa AWS independiente de MCP

**Decisión:** separar configuración, sesión, identidad, inventarios por servicio y agregación en módulos Python independientes.

**Motivo:** permite ejecutar y probar el inventario sin iniciar el servidor MCP. La integración se hará en la Fase 3.

## D-011 — STS como validación global

**Decisión:** llamar primero a `sts:GetCallerIdentity`; si no puede identificarse la cuenta, detener el inventario con un error global seguro.

**Motivo:** evita presentar resultados parciales sin saber qué identidad y cuenta se están consultando.

## D-012 — Tolerancia a fallos parciales

**Decisión:** conservar los resultados disponibles cuando falle una consulta regional o de inventario, registrando errores estructurados sin reglas por servicio.

**Motivo:** una carencia puntual de permisos no debe ocultar el inventario que sí pudo obtenerse.

## D-013 — Modelos JSON sencillos

**Decisión:** usar diccionarios tipados y normalización ISO 8601, sin añadir otra librería de modelos.

**Motivo:** el inventario es pequeño, serializable y fácil de integrar posteriormente como respuesta MCP.

## D-014 — Tool MCP como capa de presentación

**Decisión:** `listar_recursos_aws` valida parámetros, llama al agregador existente y adapta su salida, sin contener llamadas Boto3.

**Motivo:** mantiene separadas las responsabilidades del protocolo MCP y del acceso a AWS.

## D-015 — Filtrado antes de consultar servicios

**Decisión:** el agregador admite filtrar cualquier servicio reconocido por Resource Explorer. STS sigue identificando la cuenta.

**Motivo:** reduce llamadas, permisos necesarios y errores irrelevantes para la petición concreta.

## D-016 — Respuestas completas, parciales y globales

**Decisión:** devolver `ok`, `partial` o `error`, con resumen, recursos y errores normalizados. El ID de cuenta puede omitirse con `include_account_id=false`.

**Motivo:** facilita la interpretación por clientes MCP y permite anonimizar la identidad sin alterar el inventario.

## D-017 — Resource Explorer para descubrimiento general

**Decisión:** utilizar índices y vistas existentes de AWS Resource Explorer, sin crearlos ni modificarlos.

**Motivo:** descubre dinámicamente numerosos servicios sin mantener un catálogo manual de APIs.

## D-018 — Inventario uniforme

**Decisión:** representar todos los servicios con el mismo modelo y pipeline, combinando fuentes generales y adaptadores sin privilegios arquitectónicos.

**Motivo:** evita que determinados servicios tengan mayor visibilidad, semántica o fallback que el resto.

## D-019 — Índice agregador preferente

**Decisión:** preferir un índice agregador y, si no existe, combinar índices locales accesibles.

**Motivo:** evita búsquedas duplicadas y hace explícita la cobertura regional real.

## D-020 — Cobertura no universal

**Decisión:** reportar `complete_for_supported_resources`, `partial` o `unavailable`, con regiones, índices, tipos, permisos y limitaciones.

**Motivo:** ningún resultado debe interpretarse como garantía de representar cualquier entidad posible de AWS.

## D-021 — Deduplicación común

**Decisión:** identificar primero por ARN y aplicar las mismas reglas alternativas de identidad a cualquier recurso.

**Motivo:** evita duplicados sin introducir comportamiento específico por servicio.

## D-022 — Registro único de adaptadores

**Decisión:** ejecutar Lambda, S3 y los demás servicios desde un único registro que valida el contrato y las operaciones declaradas.

**Motivo:** elimina rutas legacy y permite ampliar cobertura sin cambiar el motor ni la tool MCP.

## D-023 — Modelo raíz común

**Decisión:** todos los recursos comparten los mismos campos raíz; la información particular se almacena en `details`.

**Motivo:** simplifica consumo, serialización, deduplicación, seguridad y pruebas arquitectónicas.

## D-024 — Zero-cost por defecto

**Decisión:** usar `AWS_MCP_COST_MODE=free-only` por defecto y bloquear operaciones no registradas, desconocidas, de escritura o potencialmente facturables.

**Motivo:** una operación de lectura no es necesariamente gratuita. S3, SQS y SNS contabilizan peticiones y requieren modo de confirmación más confirmación explícita.

## D-025 — Indicadores, no costes

**Decisión:** exponer únicamente indicadores potenciales de configuración con `actual_cost_confirmed=false`.

**Motivo:** sin consultar fuentes de facturación no puede afirmarse coste real, cobertura de Free Tier ni actividad.

## D-026 — Fallback uniforme

**Decisión:** cuando falle el descubrimiento general, ejecutar todos los adaptadores seleccionados que soportan descubrimiento y registrar su cobertura.

**Motivo:** evita privilegiar servicios por orden histórico de implementación.

## D-027 — Modelo de actividad semántico

**Decisión:** conservar por separado uso funcional, actividad administrativa, cambio de configuración y cambio de estado, con fecha, fuente y confianza explícitas.

**Motivo:** una operación de gestión, una modificación o un estado activo no demuestran que el recurso esté realizando su función.

## D-028 — CloudTrail Event History como fuente transversal

**Decisión:** consultar `cloudtrail:LookupEvents` una vez por región, paginar y reutilizar los eventos para correlacionarlos con todos los recursos compatibles.

**Motivo:** Event History ofrece sin cargo los eventos de administración regionales de hasta 90 días y evita multiplicar consultas por recurso. Su relación con recursos puede ser incompleta y no incluye normalmente eventos de datos.

## D-029 — Evidencia mínima y anonimizada

**Decisión:** conservar únicamente fecha, nombre y origen del evento, indicador de lectura, región, identificadores relacionados, tipo, categoría y confianza.

**Motivo:** identidad, IP, access key ID, user agent, parámetros y JSON completo no son necesarios para explicar actividad y aumentan el riesgo de exposición.

## D-030 — Inactividad conservadora

**Decisión:** usar `inactive_candidate` solo con una fuente relevante consultada, recurso suficientemente antiguo, evidencia fuera del umbral y ninguna señal reciente contradictoria; en caso de permisos insuficientes o evidencia débil se usa `unknown`.

**Motivo:** la ausencia de eventos no prueba ausencia de uso.

## D-031 — CloudWatch preparado pero bloqueado

**Decisión:** registrar `GetMetricData`, `GetMetricStatistics` y `ListMetrics` como potencialmente facturables, describir su posible enriquecimiento y no ejecutarlas en la Fase 6, incluso con `include_paid_sources=true`.

**Motivo:** pedir información avanzada no equivale a consentimiento concreto y limitado para generar posibles cargos.

## D-032 — Salud local separada de cobertura AWS

**Decisión:** mantener `health_check` rápido y limitado al estado local más una comprobación STS opcional, y delegar regiones, Resource Explorer, adaptadores, permisos y fuentes de actividad en `diagnosticar_cobertura_aws`.

**Motivo:** la ausencia de credenciales o un permiso AWS denegado no significa que el servidor MCP esté caído, y un health check no debe convertirse en inventario.

## D-033 — Registros dinámicos como fuente única

**Decisión:** registrar las tools mediante una abstracción pública propia y diagnosticar los adaptadores desde su registro común y sus metadatos.

**Motivo:** evita listas duplicadas, dependencias en internals de FastMCP y cualquier ruta especial para Lambda o S3.

## D-034 — Diagnóstico acotado y no concluyente

**Decisión:** limitar el diagnóstico a cinco regiones, no ejecutar inventario de adaptadores y distinguir operaciones permitidas por la política de permisos IAM realmente probados.

**Motivo:** la cobertura debe explicarse sin convertir el diagnóstico en una exploración lenta ni afirmar que un servicio está vacío cuando no se ha consultado.

## D-035 — Identidad mínima y anonimizada

**Decisión:** exponer únicamente disponibilidad, cuenta enmascarada y tipo general de principal.

**Motivo:** ARN, user ID, sesión, perfil y credenciales no son necesarios para explicar salud o cobertura.

## D-036 — Consentimiento efímero en la misma tool

**Decisión:** conservar la firma existente de `listar_recursos_aws` y añadir `consent_request_id`, `consent_action` y `approved_services`. El parámetro heredado de confirmación no concede permisos.

**Motivo:** mantiene compatibilidad y convierte la aprobación en un segundo paso explícito y cancelable.

## D-037 — Descubrimiento y enriquecimiento separados

**Decisión:** cada adaptador declara operaciones de descubrimiento, enriquecimiento y paginación. Aprobar `ListBuckets`, `ListQueues` o `ListTopics` no autoriza consultas de configuración.

**Motivo:** aplica mínimo privilegio a la unidad real de trabajo y evita multiplicar peticiones.

## D-038 — Grant exacto sin cambiar `free-only`

**Decisión:** mantener `free-only` y permitir una operación contabilizable únicamente mediante un grant en memoria ligado a identidad, scope, operación, región, límite, expiración y uso único.

**Motivo:** un modo global o persistente podría afectar llamadas posteriores no relacionadas.

## D-039 — Dos contadores económicos

**Decisión:** informar tanto de operaciones potencialmente facturables distintas como de peticiones SDK realmente ejecutadas.

**Motivo:** una operación puede repetirse por región o recurso y paginar.

## D-040 — Estado provisional mínimo

**Decisión:** guardar durante cinco minutos únicamente recursos normalizados y anonimizados, scope, operaciones pendientes y tokens. No se conservan respuestas Boto3 crudas ni identidad legible.

**Motivo:** permite reanudar sin repetir trabajo y reduce exposición de datos.
