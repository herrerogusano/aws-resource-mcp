"""Uniform EC2 adapter covering instances, EBS, and VPC resources."""

from typing import Any

from aws_resource_mcp.aws.adapters.base import (
    AdapterContext,
    AdapterMetadata,
    BaseAdapter,
    pages,
    selected_tags,
)
from aws_resource_mcp.models import Resource, cost_indicator, make_resource


def _arn(region: str, account_id: str | None, kind: str, identifier: str | None) -> str | None:
    if not identifier:
        return None
    return f"arn:aws:ec2:{region}:{account_id or ''}:{kind}/{identifier}"


def _name(item: dict[str, Any], fallback: str | None) -> str | None:
    return selected_tags(item.get("Tags")).get("Name") or fallback


class EC2Adapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="ec2",
        scope="regional",
        operations=tuple(
            ("ec2", operation)
            for operation in (
                "DescribeInstances",
                "DescribeVolumes",
                "DescribeVpcs",
                "DescribeSubnets",
                "DescribeNatGateways",
                "DescribeInternetGateways",
                "DescribeAddresses",
                "DescribeVpcEndpoints",
                "DescribeRouteTables",
            )
        ),
        resource_types=(
            "AWS::EC2::Instance",
            "AWS::EC2::Volume",
            "AWS::EC2::VPC",
            "AWS::EC2::Subnet",
            "AWS::EC2::NatGateway",
            "AWS::EC2::InternetGateway",
            "AWS::EC2::EIP",
            "AWS::EC2::VPCEndpoint",
            "AWS::EC2::RouteTable",
        ),
        detail_fields=("instance_type", "vpc_id", "subnet_id", "encrypted", "attachments"),
        cost_indicator_types=(
            "running_compute",
            "public_ipv4",
            "unattached_volume",
            "provisioned_iops",
            "nat_gateway",
            "unassociated_elastic_ip",
            "billable_vpc_endpoint",
        ),
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        resources: list[Resource] = []
        for region in self.regions(context):
            resources.extend(self._instances(context, region))
            resources.extend(self._volumes(context, region))
            resources.extend(self._network(context, region))
        return resources

    def _instances(self, context: AdapterContext, region: str) -> list[Resource]:
        reservations = pages(
            context, "ec2", "DescribeInstances", "Reservations", region=region
        )
        resources: list[Resource] = []
        for reservation in reservations:
            for instance in reservation.get("Instances", []):
                identifier = instance.get("InstanceId")
                state = instance.get("State", {}).get("Name")
                indicators = []
                if context.include_cost_indicators and state == "running":
                    indicators.append(
                        cost_indicator(
                            "running_compute", "high", "A running compute instance can generate charges."
                        )
                    )
                if context.include_cost_indicators and instance.get("PublicIpAddress"):
                    indicators.append(
                        cost_indicator(
                            "public_ipv4", "medium", "An attached public IPv4 address can generate charges."
                        )
                    )
                details = {
                    "instance_type": instance.get("InstanceType"),
                    "architecture": instance.get("Architecture"),
                    "vpc_id": instance.get("VpcId"),
                    "subnet_id": instance.get("SubnetId"),
                    "security_group_ids": [group.get("GroupId") for group in instance.get("SecurityGroups", [])],
                    "public_ip_present": bool(instance.get("PublicIpAddress")),
                    "volume_ids": [
                        mapping.get("Ebs", {}).get("VolumeId")
                        for mapping in instance.get("BlockDeviceMappings", [])
                        if mapping.get("Ebs", {}).get("VolumeId")
                    ],
                    "tags": selected_tags(instance.get("Tags")),
                } if context.include_details else {}
                resources.append(
                    make_resource(
                        service="ec2",
                        resource_type="AWS::EC2::Instance",
                        region=region,
                        source="ec2_api",
                        identifier=identifier,
                        arn=_arn(region, context.account_id, "instance", identifier),
                        name=_name(instance, identifier),
                        account_id=context.account_id,
                        state=state,
                        created_at=instance.get("LaunchTime"),
                        details=details,
                        cost_indicators=indicators,
                    )
                )
        return resources

    def _volumes(self, context: AdapterContext, region: str) -> list[Resource]:
        volumes = pages(context, "ec2", "DescribeVolumes", "Volumes", region=region)
        resources: list[Resource] = []
        for volume in volumes:
            identifier = volume.get("VolumeId")
            indicators = []
            if context.include_cost_indicators and not volume.get("Attachments"):
                indicators.append(
                    cost_indicator(
                        "unattached_volume", "medium", "An unattached volume can continue generating storage charges."
                    )
                )
            if context.include_cost_indicators and volume.get("VolumeType") in {"io1", "io2"}:
                indicators.append(
                    cost_indicator(
                        "provisioned_iops", "medium", "Provisioned IOPS storage can generate additional charges."
                    )
                )
            details = {
                "volume_type": volume.get("VolumeType"),
                "size_gib": volume.get("Size"),
                "encrypted": volume.get("Encrypted"),
                "attachments": [item.get("InstanceId") for item in volume.get("Attachments", [])],
                "iops": volume.get("Iops"),
                "throughput": volume.get("Throughput"),
                "tags": selected_tags(volume.get("Tags")),
            } if context.include_details else {}
            resources.append(
                make_resource(
                    service="ec2",
                    resource_type="AWS::EC2::Volume",
                    region=region,
                    source="ec2_api",
                    identifier=identifier,
                    arn=_arn(region, context.account_id, "volume", identifier),
                    name=_name(volume, identifier),
                    account_id=context.account_id,
                    state=volume.get("State"),
                    created_at=volume.get("CreateTime"),
                    details=details,
                    cost_indicators=indicators,
                )
            )
        return resources

    def _network(self, context: AdapterContext, region: str) -> list[Resource]:
        collections = {
            "vpc": ("DescribeVpcs", "Vpcs", "AWS::EC2::VPC", "VpcId"),
            "subnet": ("DescribeSubnets", "Subnets", "AWS::EC2::Subnet", "SubnetId"),
            "natgateway": ("DescribeNatGateways", "NatGateways", "AWS::EC2::NatGateway", "NatGatewayId"),
            "internet-gateway": ("DescribeInternetGateways", "InternetGateways", "AWS::EC2::InternetGateway", "InternetGatewayId"),
            "vpc-endpoint": ("DescribeVpcEndpoints", "VpcEndpoints", "AWS::EC2::VPCEndpoint", "VpcEndpointId"),
            "route-table": ("DescribeRouteTables", "RouteTables", "AWS::EC2::RouteTable", "RouteTableId"),
        }
        resources: list[Resource] = []
        for kind, (operation, key, resource_type, id_key) in collections.items():
            for item in pages(context, "ec2", operation, key, region=region):
                identifier = item.get(id_key)
                indicators = []
                if context.include_cost_indicators and kind == "natgateway":
                    indicators.append(cost_indicator("nat_gateway", "high", "A NAT Gateway can generate hourly and data-processing charges."))
                if context.include_cost_indicators and kind == "vpc-endpoint" and item.get("VpcEndpointType") != "Gateway":
                    indicators.append(cost_indicator("billable_vpc_endpoint", "medium", "This VPC endpoint type can generate hourly and data-processing charges."))
                details = {
                    "vpc_id": item.get("VpcId"),
                    "subnet_id": item.get("SubnetId"),
                    "state": item.get("State"),
                    "cidr_block": item.get("CidrBlock"),
                    "endpoint_type": item.get("VpcEndpointType"),
                    "attachments_count": len(item.get("Attachments", [])),
                    "routes_count": len(item.get("Routes", [])),
                    "tags": selected_tags(item.get("Tags")),
                } if context.include_details else {}
                resources.append(
                    make_resource(
                        service="ec2",
                        resource_type=resource_type,
                        region=region,
                        source="ec2_api",
                        identifier=identifier,
                        arn=_arn(region, context.account_id, kind, identifier),
                        name=_name(item, identifier),
                        account_id=context.account_id,
                        state=item.get("State") or "available",
                        created_at=item.get("CreateTime"),
                        details=details,
                        cost_indicators=indicators,
                    )
                )
        addresses = pages(context, "ec2", "DescribeAddresses", "Addresses", region=region)
        for address in addresses:
            identifier = address.get("AllocationId") or address.get("PublicIp")
            indicators = []
            if context.include_cost_indicators and not address.get("AssociationId"):
                indicators.append(cost_indicator("unassociated_elastic_ip", "medium", "An unassociated Elastic IP can generate charges."))
            resources.append(
                make_resource(
                    service="ec2",
                    resource_type="AWS::EC2::EIP",
                    region=region,
                    source="ec2_api",
                    identifier=identifier,
                    arn=_arn(region, context.account_id, "elastic-ip", identifier),
                    name=identifier,
                    account_id=context.account_id,
                    state="associated" if address.get("AssociationId") else "unassociated",
                    details={
                        "association_id": address.get("AssociationId"),
                        "network_interface_id": address.get("NetworkInterfaceId"),
                    } if context.include_details else {},
                    cost_indicators=indicators,
                )
            )
        return resources
