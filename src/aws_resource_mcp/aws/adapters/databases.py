"""RDS, Aurora, and DynamoDB adapters."""

from aws_resource_mcp.aws.adapters.base import (
    AdapterContext,
    AdapterMetadata,
    BaseAdapter,
    pages,
)
from aws_resource_mcp.models import Resource, cost_indicator, make_resource


class RDSAdapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="rds",
        scope="regional",
        operations=(
            ("rds", "DescribeDBInstances"),
            ("rds", "DescribeDBClusters"),
            ("rds", "DescribeDBSnapshots"),
        ),
        resource_types=("AWS::RDS::DBInstance", "AWS::RDS::DBCluster", "AWS::RDS::DBSnapshot"),
        detail_fields=("engine", "engine_version", "instance_class", "storage_gib", "multi_az"),
        cost_indicator_types=("running_database", "multi_az", "provisioned_iops", "manual_snapshot"),
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        resources: list[Resource] = []
        for region in self.regions(context):
            for item in pages(context, "rds", "DescribeDBInstances", "DBInstances", region=region, request_token="Marker", response_token="Marker"):
                status = item.get("DBInstanceStatus")
                indicators = []
                if context.include_cost_indicators and status not in {"stopped", "stopping"}:
                    indicators.append(cost_indicator("running_database", "high", "An available database instance can generate compute and storage charges."))
                if context.include_cost_indicators and item.get("MultiAZ"):
                    indicators.append(cost_indicator("multi_az", "medium", "Multi-AZ deployment provisions additional database capacity."))
                if context.include_cost_indicators and item.get("Iops"):
                    indicators.append(cost_indicator("provisioned_iops", "medium", "Provisioned database IOPS can generate additional charges."))
                identifier = item.get("DBInstanceIdentifier")
                resources.append(make_resource(
                    service="rds", resource_type="AWS::RDS::DBInstance", region=region,
                    source="rds_api", identifier=identifier, arn=item.get("DBInstanceArn"),
                    name=identifier, account_id=context.account_id, state=status,
                    created_at=item.get("InstanceCreateTime"),
                    details={
                        "engine": item.get("Engine"), "engine_version": item.get("EngineVersion"),
                        "instance_class": item.get("DBInstanceClass"), "storage_gib": item.get("AllocatedStorage"),
                        "storage_type": item.get("StorageType"), "iops": item.get("Iops"),
                        "multi_az": item.get("MultiAZ"), "publicly_accessible": item.get("PubliclyAccessible"),
                        "encrypted": item.get("StorageEncrypted"), "backup_retention_days": item.get("BackupRetentionPeriod"),
                    } if context.include_details else {}, cost_indicators=indicators,
                ))
            for item in pages(context, "rds", "DescribeDBClusters", "DBClusters", region=region, request_token="Marker", response_token="Marker"):
                status = item.get("Status")
                indicators = []
                if context.include_cost_indicators and status not in {"stopped", "stopping"}:
                    indicators.append(cost_indicator("running_database", "high", "An active database cluster can generate compute and storage charges."))
                identifier = item.get("DBClusterIdentifier")
                resources.append(make_resource(
                    service="rds", resource_type="AWS::RDS::DBCluster", region=region,
                    source="rds_api", identifier=identifier, arn=item.get("DBClusterArn"), name=identifier,
                    account_id=context.account_id, state=status, created_at=item.get("ClusterCreateTime"),
                    details={
                        "engine": item.get("Engine"), "engine_version": item.get("EngineVersion"),
                        "engine_mode": item.get("EngineMode"), "members_count": len(item.get("DBClusterMembers", [])),
                        "multi_az": item.get("MultiAZ"), "storage_encrypted": item.get("StorageEncrypted"),
                        "backup_retention_days": item.get("BackupRetentionPeriod"),
                    } if context.include_details else {}, cost_indicators=indicators,
                ))
            for item in pages(
                context, "rds", "DescribeDBSnapshots", "DBSnapshots", region=region,
                parameters={"SnapshotType": "manual"}, request_token="Marker", response_token="Marker",
            ):
                identifier = item.get("DBSnapshotIdentifier")
                indicators = [cost_indicator("manual_snapshot", "low", "A retained manual snapshot consumes database backup storage.")] if context.include_cost_indicators else []
                resources.append(make_resource(
                    service="rds", resource_type="AWS::RDS::DBSnapshot", region=region,
                    source="rds_api", identifier=identifier, arn=item.get("DBSnapshotArn"), name=identifier,
                    account_id=context.account_id, state=item.get("Status"), created_at=item.get("SnapshotCreateTime"),
                    details={"engine": item.get("Engine"), "allocated_storage_gib": item.get("AllocatedStorage"), "encrypted": item.get("Encrypted")} if context.include_details else {},
                    cost_indicators=indicators,
                ))
        return resources


class DynamoDBAdapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="dynamodb",
        scope="regional",
        operations=(("dynamodb", "ListTables"), ("dynamodb", "DescribeTable"), ("dynamodb", "DescribeContinuousBackups")),
        resource_types=("AWS::DynamoDB::Table",),
        detail_fields=("billing_mode", "provisioned_throughput", "table_size_bytes", "item_count", "streams", "continuous_backups", "replicas"),
        cost_indicator_types=("provisioned_capacity", "continuous_backups", "global_replication", "significant_storage"),
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        resources: list[Resource] = []
        for region in self.regions(context):
            names = pages(
                context, "dynamodb", "ListTables", "TableNames", region=region,
                request_token="ExclusiveStartTableName", response_token="LastEvaluatedTableName",
            )
            for name in names:
                table = context.call("dynamodb", "DescribeTable", region=region, TableName=name).get("Table", {})
                backup = context.call("dynamodb", "DescribeContinuousBackups", region=region, TableName=name).get("ContinuousBackupsDescription", {})
                billing_mode = table.get("BillingModeSummary", {}).get("BillingMode") or "PROVISIONED"
                backup_status = backup.get("PointInTimeRecoveryDescription", {}).get("PointInTimeRecoveryStatus")
                size = table.get("TableSizeBytes") or 0
                replicas = table.get("Replicas", [])
                indicators = []
                if context.include_cost_indicators and billing_mode == "PROVISIONED":
                    indicators.append(cost_indicator("provisioned_capacity", "medium", "Provisioned table capacity can generate charges even when idle."))
                if context.include_cost_indicators and backup_status == "ENABLED":
                    indicators.append(cost_indicator("continuous_backups", "low", "Point-in-time recovery can generate backup charges."))
                if context.include_cost_indicators and replicas:
                    indicators.append(cost_indicator("global_replication", "high", "Global table replicas multiply regional storage and request usage."))
                if context.include_cost_indicators and size >= 10 * 1024**3:
                    indicators.append(cost_indicator("significant_storage", "medium", "The reported table size indicates significant storage usage."))
                resources.append(make_resource(
                    service="dynamodb", resource_type="AWS::DynamoDB::Table", region=region,
                    source="dynamodb_api", identifier=table.get("TableId") or name, arn=table.get("TableArn"),
                    name=name, account_id=context.account_id, state=table.get("TableStatus"), created_at=table.get("CreationDateTime"),
                    details={
                        "billing_mode": billing_mode,
                        "provisioned_throughput": {
                            "read": table.get("ProvisionedThroughput", {}).get("ReadCapacityUnits"),
                            "write": table.get("ProvisionedThroughput", {}).get("WriteCapacityUnits"),
                        },
                        "table_size_bytes": size, "item_count": table.get("ItemCount"),
                        "encrypted": table.get("SSEDescription", {}).get("Status") == "ENABLED",
                        "streams": bool(table.get("LatestStreamArn")), "continuous_backups": backup_status,
                        "replicas": [item.get("RegionName") for item in replicas],
                    } if context.include_details else {}, cost_indicators=indicators,
                ))
        return resources
