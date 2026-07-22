"""IAM, CloudFront, and Route 53 global adapters."""

from aws_resource_mcp.aws.adapters.base import AdapterContext, AdapterMetadata, BaseAdapter, pages
from aws_resource_mcp.models import Resource, cost_indicator, make_resource


class IAMAdapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="iam", scope="global",
        operations=(("iam", "ListUsers"), ("iam", "ListRoles"), ("iam", "ListPolicies")),
        resource_types=("AWS::IAM::User", "AWS::IAM::Role", "AWS::IAM::ManagedPolicy"),
        detail_fields=("last_used_at", "attached_policies_count", "permissions_boundary"),
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        resources: list[Resource] = []
        for user in pages(context, "iam", "ListUsers", "Users", request_token="Marker", response_token="Marker"):
            resources.append(make_resource(
                service="iam", resource_type="AWS::IAM::User", region="global", source="iam_api",
                identifier=user.get("UserId"), arn=user.get("Arn"), name=user.get("UserName"),
                account_id=context.account_id, state="active", created_at=user.get("CreateDate"),
                details={"password_last_used": user.get("PasswordLastUsed").isoformat() if hasattr(user.get("PasswordLastUsed"), "isoformat") else user.get("PasswordLastUsed"), "permissions_boundary": bool(user.get("PermissionsBoundary"))} if context.include_details else {},
            ))
        for role in pages(context, "iam", "ListRoles", "Roles", request_token="Marker", response_token="Marker"):
            last_used = role.get("RoleLastUsed", {})
            resources.append(make_resource(
                service="iam", resource_type="AWS::IAM::Role", region="global", source="iam_api",
                identifier=role.get("RoleId"), arn=role.get("Arn"), name=role.get("RoleName"),
                account_id=context.account_id, state="active", created_at=role.get("CreateDate"),
                details={"last_used_at": last_used.get("LastUsedDate").isoformat() if hasattr(last_used.get("LastUsedDate"), "isoformat") else last_used.get("LastUsedDate"), "last_used_region": last_used.get("Region"), "max_session_duration": role.get("MaxSessionDuration"), "permissions_boundary": bool(role.get("PermissionsBoundary"))} if context.include_details else {},
            ))
        for policy in pages(context, "iam", "ListPolicies", "Policies", parameters={"Scope": "Local"}, request_token="Marker", response_token="Marker"):
            resources.append(make_resource(
                service="iam", resource_type="AWS::IAM::ManagedPolicy", region="global", source="iam_api",
                identifier=policy.get("PolicyId"), arn=policy.get("Arn"), name=policy.get("PolicyName"),
                account_id=context.account_id, state="attached" if policy.get("AttachmentCount") else "unattached",
                created_at=policy.get("CreateDate"),
                details={"attachment_count": policy.get("AttachmentCount"), "permissions_boundary_usage_count": policy.get("PermissionsBoundaryUsageCount"), "updated_at": policy.get("UpdateDate").isoformat() if hasattr(policy.get("UpdateDate"), "isoformat") else policy.get("UpdateDate")} if context.include_details else {},
            ))
        return resources


class CloudFrontAdapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="cloudfront", scope="global",
        operations=(("cloudfront", "ListDistributions"),),
        resource_types=("AWS::CloudFront::Distribution",),
        detail_fields=("enabled", "price_class", "origins_count", "aliases_count"),
        cost_indicator_types=("enabled_distribution",),
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        distributions = pages(
            context, "cloudfront", "ListDistributions", "DistributionList",
            request_token="Marker", response_token="NextMarker",
        )
        resources: list[Resource] = []
        for item in distributions:
            identifier = item.get("Id")
            enabled = bool(item.get("Enabled"))
            indicators = [cost_indicator("enabled_distribution", "medium", "An enabled distribution can generate request and data-transfer charges.")] if context.include_cost_indicators and enabled else []
            resources.append(make_resource(
                service="cloudfront", resource_type="AWS::CloudFront::Distribution", region="global",
                source="cloudfront_api", identifier=identifier, arn=item.get("ARN"), name=identifier,
                account_id=context.account_id, state=item.get("Status"), created_at=item.get("LastModifiedTime"),
                details={"enabled": enabled, "price_class": item.get("PriceClass"), "origins_count": item.get("Origins", {}).get("Quantity"), "aliases_count": item.get("Aliases", {}).get("Quantity"), "http_version": item.get("HttpVersion"), "ipv6_enabled": item.get("IsIPV6Enabled")} if context.include_details else {},
                cost_indicators=indicators,
            ))
        return resources


class Route53Adapter(BaseAdapter):
    metadata = AdapterMetadata(
        service_name="route53", scope="global",
        operations=(("route53", "ListHostedZones"),),
        resource_types=("AWS::Route53::HostedZone",),
        detail_fields=("private_zone", "record_count"),
        cost_indicator_types=("hosted_zone",),
    )

    def discover(self, context: AdapterContext) -> list[Resource]:
        zones = pages(context, "route53", "ListHostedZones", "HostedZones", request_token="Marker", response_token="NextMarker")
        resources: list[Resource] = []
        for zone in zones:
            raw_id = zone.get("Id")
            identifier = raw_id.rsplit("/", 1)[-1] if raw_id else None
            indicators = [cost_indicator("hosted_zone", "low", "A hosted zone can generate recurring and query charges.")] if context.include_cost_indicators else []
            resources.append(make_resource(
                service="route53", resource_type="AWS::Route53::HostedZone", region="global",
                source="route53_api", identifier=identifier,
                arn=f"arn:aws:route53:::hostedzone/{identifier}" if identifier else None,
                name=zone.get("Name"), account_id=context.account_id, state="available",
                details={"private_zone": zone.get("Config", {}).get("PrivateZone"), "record_count": zone.get("ResourceRecordSetCount")} if context.include_details else {},
                cost_indicators=indicators,
            ))
        return resources
