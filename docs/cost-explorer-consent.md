# Consentimiento de Cost Explorer

La documentación principal está en [Análisis económico](economic-analysis.md).
Solo `ce:GetCostAndUsage` entra en `consented-readonly`. La política IAM permite
que un rol dedicado pueda ejecutar la capacidad, pero el guard exige además un
consentimiento efímero, ligado al alcance y limitado a una petición. Forecast y
detalle por recurso están excluidos.
