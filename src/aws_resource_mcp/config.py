"""Non-sensitive runtime configuration for AWS access."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_AWS_REGION = "eu-west-1"
DEFAULT_COST_MODE = "free-only"
DEFAULT_MAX_REQUESTS_PER_TOOL = 250
VALID_COST_MODES = frozenset({"free-only", "allow-paid-with-confirmation"})


@dataclass(frozen=True)
class AWSConfig:
    """AWS region and optional shared-configuration profile name."""

    region: str = DEFAULT_AWS_REGION
    profile_name: str | None = None
    cost_mode: str = DEFAULT_COST_MODE
    max_requests_per_tool: int = DEFAULT_MAX_REQUESTS_PER_TOOL

    @classmethod
    def from_sources(
        cls,
        *,
        region: str | None = None,
        profile_name: str | None = None,
        cost_mode: str | None = None,
        max_requests_per_tool: int | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "AWSConfig":
        """Build configuration from explicit values and standard AWS variables."""
        values = os.environ if environ is None else environ
        resolved_region = (
            region
            or values.get("AWS_REGION")
            or values.get("AWS_DEFAULT_REGION")
            or DEFAULT_AWS_REGION
        )
        resolved_profile = profile_name or values.get("AWS_PROFILE") or None
        resolved_cost_mode = (
            cost_mode or values.get("AWS_MCP_COST_MODE") or DEFAULT_COST_MODE
        )
        raw_max_requests = (
            max_requests_per_tool
            if max_requests_per_tool is not None
            else values.get(
                "AWS_MCP_MAX_REQUESTS_PER_TOOL", DEFAULT_MAX_REQUESTS_PER_TOOL
            )
        )
        try:
            resolved_max_requests = int(raw_max_requests)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "AWS_MCP_MAX_REQUESTS_PER_TOOL must be a positive integer"
            ) from error
        if resolved_max_requests < 1:
            raise ValueError("AWS_MCP_MAX_REQUESTS_PER_TOOL must be a positive integer")
        if resolved_cost_mode not in VALID_COST_MODES:
            raise ValueError(
                "AWS_MCP_COST_MODE must be free-only or allow-paid-with-confirmation"
            )
        return cls(
            region=resolved_region,
            profile_name=resolved_profile,
            cost_mode=resolved_cost_mode,
            max_requests_per_tool=resolved_max_requests,
        )
