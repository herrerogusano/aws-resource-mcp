# Configuración IAM manual

Esta guía describe una configuración recomendada; el proyecto no ejecuta estos
pasos.

1. Crear manualmente un rol dedicado exclusivamente al MCP.
2. Definir una relación de confianza restringida al usuario o rol humano que
   vaya a asumirlo. Evitar principales generales.
3. Adjuntar la política `free-only` o, si se necesita el flujo de consentimiento,
   la política `combined-readonly`.
4. Opcionalmente aplicar la permissions boundary para impedir que futuras
   políticas amplíen la capacidad más allá del máximo actual.
5. Usar credenciales temporales mediante `AssumeRole`, AWS IAM Identity Center
   o un perfil externo. No guardar access keys en el repositorio.
6. Seleccionar el perfil con `AWS_PROFILE` o la configuración local del cliente
   MCP y comprobar la identidad enmascarada con `health_check`.
7. Revisar periódicamente el manifiesto y regenerar las políticas cuando cambie
   el registro de operaciones.

Dos configuraciones son válidas:

- Práctica: adjuntar las políticas `free-only` y `consented-readonly`; el guard
  limita la segunda en cada ejecución.
- IAM estricta: adjuntar solo `free-only`; una operación consentida seguirá
  devolviendo `permission_denied` hasta que el operador cambie manualmente la
  configuración.

Ejemplo conceptual de perfil local, fuera del repositorio:

```ini
[profile aws-resource-mcp]
role_arn = arn:aws:iam::<ACCOUNT_ID>:role/aws-resource-mcp-readonly
source_profile = <LOCAL_SOURCE_PROFILE>
region = eu-west-1
```

No deben copiarse valores reales a documentación, incidencias o resultados de
prueba. El proyecto no inspecciona políticas adjuntas ni puede afirmar que la
identidad actual sea dedicada; por eso health y diagnóstico muestran ese dato
como `unknown`.

Adjuntar una política restrictiva a una identidad que ya dispone de
`AdministratorAccess`, `PowerUserAccess`, `ReadOnlyAccess`, `SecurityAudit` u
otras políticas no reduce sus permisos efectivos. Se recomienda una identidad
dedicada sin políticas ajenas al MCP. La boundary limita el máximo concedible,
pero no concede permisos y no neutraliza por sí sola todas las políticas
basadas en recursos.

Configuración conceptual compatible con Codex, MCP Inspector y ejecución
directa:

```text
AWS_PROFILE=aws-resource-mcp-readonly
AWS_MCP_COST_MODE=free-only
```

El nombre es un ejemplo, no una modificación del perfil actual.

Access Analyzer `ValidatePolicy` y `iam:SimulateCustomPolicy` podrían aportar
validación remota, pero se mantienen bloqueados hasta verificar su clasificación
económica. En esta fase solo se ejecuta validación local.

Comandos manuales equivalentes, deliberadamente no ejecutados:

```powershell
aws accessanalyzer validate-policy --policy-type IDENTITY_POLICY `
  --policy-document file://iam/aws-resource-mcp-combined-readonly.json

aws iam simulate-custom-policy `
  --policy-input-list file://iam/aws-resource-mcp-combined-readonly.json `
  --action-names ec2:DescribeInstances ec2:TerminateInstances
```

El simulador no reproduce todas las capas de evaluación IAM y no sustituye una
revisión. Ambos comandos requieren permisos y solo deben utilizarse después de
verificar su coste y alcance.
