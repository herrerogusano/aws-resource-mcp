# Adaptadores de servicios

## Registro

| Adaptador | Ámbito | Recursos principales |
|---|---|---|
| Lambda | Regional | Funciones |
| S3 | Global | Buckets |
| EC2 | Regional | Instancias, volúmenes, VPC, subnets, NAT, IGW, EIP, endpoints y rutas |
| RDS | Regional | Instancias, clústeres Aurora y snapshots manuales |
| DynamoDB | Regional | Tablas |
| ECS | Regional | Clústeres, servicios y tareas/Fargate |
| API Gateway | Regional | REST, HTTP y WebSocket APIs |
| CloudFormation | Regional | Stacks activos |
| SQS | Regional | Colas |
| SNS | Regional | Topics |
| IAM | Global | Usuarios, roles y políticas administradas por la cuenta |
| CloudFront | Global | Distribuciones |
| Route 53 | Global | Hosted zones |

Todos implementan el mismo contrato, se seleccionan con el mismo filtro y se ejecutan mediante el mismo motor. Cada adaptador declara operaciones, tipos, alcance, capacidades, campos de detalle e indicadores.

El diagnóstico de cobertura lee ese mismo registro. Para cada adaptador informa alcance, descubrimiento, enriquecimiento, indicadores, señales gratuitas de actividad, operaciones requeridas, permitidas y bloqueadas, regiones aplicables y limitaciones. No ejecuta un inventario para probar permisos.

Lambda y S3 se implementaron antes que los demás, pero fueron migrados al registro. No existen imports desde la tool, listas legacy, respuestas raíz especiales, deduplicación privada ni fallback exclusivo.

## Modelo producido

```json
{
  "id": null,
  "arn": null,
  "name": null,
  "service": "example",
  "resource_type": "AWS::Example::Resource",
  "region": "eu-west-1",
  "account_id": null,
  "state": null,
  "created_at": null,
  "sources": [],
  "details": {},
  "cost_indicators": [],
  "activity": {"status": "unknown"}
}
```

Los adaptadores no devuelven código, variables de entorno, objetos S3, mensajes, endpoints SNS, plantillas, parámetros sensibles, documentos de política ni registros DNS completos.

Los indicadores describen configuraciones como cómputo activo, almacenamiento versionado, réplicas, capacidad provisionada, NAT Gateway o recursos no asociados. Son señales potenciales y nunca confirman gasto.

## Contrato de actividad

Todos los adaptadores implementan `get_free_activity_signals(resources, context)`. La implementación base normaliza fecha de creación, estado y los campos de actividad declarados en `AdapterMetadata`; ningún adaptador llama directamente a CloudTrail o CloudWatch.

- Lambda declara `LastModified` como cambio de configuración, nunca como última invocación.
- IAM puede declarar `RoleLastUsed` o `PasswordLastUsed` como uso funcional oficial.
- CloudFormation y CloudFront declaran sus fechas de actualización como cambios de configuración.
- EC2/EBS, RDS, ECS/Fargate y los demás conservan creación y estado como señales indirectas cuando no existe un campo de uso fiable.
- S3 no lista objetos ni afirma conocer su último acceso; SQS no recibe mensajes; SNS no publica; DynamoDB no ejecuta `Scan` ni `Query`; RDS no abre conexiones.

El motor común correlaciona después estas señales con eventos CloudTrail normalizados. Lambda, S3, EC2, RDS y el resto atraviesan exactamente el mismo registro, método, clasificador, política de costes, modelo de error y construcción de resultados.

Un test arquitectónico compara la estructura diagnóstica de Lambda, S3, EC2 y RDS. S3 puede quedar `blocked_by_cost_policy` por sus operaciones declaradas, pero no recibe una ruta diagnóstica diferente.
