"""AWS session construction without import-time clients or network calls."""

from collections.abc import Callable

import boto3
from boto3.session import Session

from aws_resource_mcp.config import DEFAULT_AWS_REGION


def create_aws_session(
    region: str = DEFAULT_AWS_REGION,
    profile_name: str | None = None,
    *,
    session_factory: Callable[..., Session] = boto3.Session,
) -> Session:
    """Create a Boto3 session using its standard credential resolution chain."""
    options: dict[str, str] = {"region_name": region}
    if profile_name:
        options["profile_name"] = profile_name
    return session_factory(**options)
