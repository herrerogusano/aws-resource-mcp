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
  "activity": {"status": "not_analyzed"}
}
```

Los adaptadores no devuelven código, variables de entorno, objetos S3, mensajes, endpoints SNS, plantillas, parámetros sensibles, documentos de política ni registros DNS completos.

Los indicadores describen configuraciones como cómputo activo, almacenamiento versionado, réplicas, capacidad provisionada, NAT Gateway o recursos no asociados. Son señales potenciales y nunca confirman gasto.
