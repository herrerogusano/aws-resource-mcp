# Matriz de permisos IAM

La fuente de verdad es `iam/permissions-manifest.json`. Esta vista resume las
capacidades; el manifiesto conserva el detalle de cada operación.

| Capacidad | Servicios | Política | Riesgo | Observación |
| --- | --- | --- | --- | --- |
| Identidad | STS | Excluida | Bajo | `GetCallerIdentity` no necesita `Allow` explícito |
| Regiones e inventario general | EC2, Resource Explorer | Free-only | Bajo | Lecturas regionales |
| Adaptadores de inventario | Lambda, EC2, RDS, DynamoDB, ECS, API Gateway, CloudFormation, IAM, CloudFront, Route 53 | Free-only | Bajo/medio | Mismo registro y guard |
| Actividad administrativa | CloudTrail | Free-only | Bajo | Event History, máximo 90 días |
| Free Tier | Free Tier API | Free-only | Medio | Datos económicos de cuenta minimizados |
| Inventario contabilizable | S3, SQS, SNS | Consented-readonly | Bajo | El permiso IAM no omite el consentimiento |
| Coste real agregado | Cost Explorer | Consented-readonly | Medio | Solo `GetCostAndUsage`, una petición autorizada |
| Métricas funcionales | CloudWatch | Excluida | Bajo | Flujo de consentimiento no implementado |
| Validación remota | Access Analyzer, IAM Simulator | Excluida | Desconocido/medio | Coste no verificado; no ejecutada |

## Reglas de alcance

Las enumeraciones de cuenta y las operaciones que descubren recursos antes de
conocer sus ARN requieren `Resource: "*"`. Cada caso incluye una justificación
en el manifiesto. Cuando una API admite ARN pero el MCP descubre recursos
dinámicamente, el artefacto portable también usa `*`; un operador puede crear
una variante más estrecha con una allowlist de ARN revisada.

Las acciones alternativas, como compatibilidad histórica de facturación o
autorizaciones de replicación de tablas globales, son informativas. No forman
parte de ninguna política generada.
