# IAM de mínimo privilegio

## Alcance

El MCP no crea, modifica ni adjunta políticas. Los documentos de `iam/` son
artefactos locales y revisables derivados del registro real de operaciones. La
configuración de una identidad AWS sigue siendo una acción manual del operador.

## Políticas generadas

- `aws-resource-mcp-free-only.json`: operaciones de lectura clasificadas como
  gratuitas y habilitadas en `free-only`.
- `aws-resource-mcp-consented-readonly.json`: operaciones de lectura
  potencialmente facturables que la aplicación solo ejecuta tras un
  consentimiento efímero y acotado.
- `aws-resource-mcp-combined-readonly.json`: unión de las dos anteriores para
  una identidad de ejecución dedicada.
- `aws-resource-mcp-permissions-boundary.json`: boundary opcional equivalente
  al máximo funcional actual. No concede permisos por sí misma.
- `permissions-manifest.json`: trazabilidad de operación Boto3, acción IAM,
  capacidad, consumidor, alcance, riesgo, coste, referencia y exclusión.

Tener permiso IAM no equivale a tener consentimiento de aplicación. Por
ejemplo, `s3:ListAllMyBuckets` puede existir en la política combinada, pero el
guard seguirá bloqueando `ListBuckets` hasta que exista una aprobación puntual.

## Exclusiones deliberadas

No se conceden escrituras, comodines de acción, acceso a secretos o contenido,
invocaciones, lectura de objetos, recepción de mensajes, consultas de datos ni
logs. CloudWatch, forecast de Cost Explorer, detalle de coste por recurso,
Access Analyzer y el simulador IAM permanecen fuera de las políticas de
ejecución.

`sts:GetCallerIdentity` aparece en el manifiesto pero no en las políticas:
AWS documenta que esta operación devuelve la identidad incluso sin un `Allow`
explícito. Las acciones alternativas o dependientes del contexto también se
documentan por separado y no se conceden automáticamente.

## Generación y validación local

```powershell
uv run aws-resource-mcp-generate-iam
uv run aws-resource-mcp-generate-iam --check
```

El generador no usa credenciales ni contacta con AWS. Falla ante metadatos sin
verificar, operaciones de escritura, riesgo sensible alto, costes desconocidos
incluidos o acciones con comodín. La salida es determinista y los tests
comprueban que el código Boto3 no eluda el guard central.

Opcionalmente se pueden generar copias limitadas por región:

```powershell
uv run aws-resource-mcp-generate-iam --output-dir .local-iam `
  --allowed-region eu-west-1
```

Las políticas versionadas no fijan una región para conservar el inventario
multirregional. La restricción regional es una decisión de despliegue.

## Referencias

Las acciones se verificaron el 23 de julio de 2026 contra la referencia
oficial de autorización de servicios de AWS y su versión legible por máquinas.
La fecha y URL exactas se conservan por operación en el manifiesto.
