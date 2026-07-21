"""Read-only Lambda function inventory."""

from typing import Any

from aws_resource_mcp.models import to_iso8601


def list_lambda_functions(session: Any, region: str) -> list[dict[str, Any]]:
    """List and normalize every Lambda function visible in the selected region."""
    client = session.client("lambda", region_name=region)
    paginator = client.get_paginator("list_functions")
    functions: list[dict[str, Any]] = []

    for page in paginator.paginate():
        for function in page.get("Functions", []):
            functions.append(
                {
                    "name": function.get("FunctionName"),
                    "arn": function.get("FunctionArn"),
                    "runtime": function.get("Runtime"),
                    "architectures": list(function.get("Architectures", [])),
                    "memory_size": function.get("MemorySize"),
                    "timeout": function.get("Timeout"),
                    "code_size": function.get("CodeSize"),
                    "last_modified": to_iso8601(function.get("LastModified")),
                    "package_type": function.get("PackageType"),
                }
            )
    return functions
