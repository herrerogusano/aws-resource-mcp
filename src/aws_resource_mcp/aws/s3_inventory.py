"""Read-only S3 bucket inventory."""

from typing import Any

from aws_resource_mcp.aws.errors import describe_aws_error
from aws_resource_mcp.models import InventoryError, to_iso8601


def list_s3_buckets(
    session: Any,
) -> tuple[list[dict[str, str | None]], list[InventoryError]]:
    """List buckets and their regions while preserving per-bucket failures."""
    client = session.client("s3")
    response = client.list_buckets()
    buckets: list[dict[str, str | None]] = []
    errors: list[InventoryError] = []

    for bucket in response.get("Buckets", []):
        name = bucket.get("Name")
        region: str | None = None
        if name:
            try:
                location = client.get_bucket_location(Bucket=name).get(
                    "LocationConstraint"
                )
                region = "us-east-1" if location is None else str(location)
            except Exception as error:
                bucket_error = describe_aws_error("s3", error)
                bucket_error["message"] = (
                    f"Could not determine the region for bucket {name!r}. "
                    + bucket_error["message"]
                )
                errors.append(bucket_error)

        buckets.append(
            {
                "name": name,
                "creation_date": to_iso8601(bucket.get("CreationDate")),
                "region": region,
            }
        )

    return buckets, errors
