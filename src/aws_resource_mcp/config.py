"""Non-sensitive runtime configuration for AWS access."""

from dataclasses import dataclass
import os
from typing import Mapping

DEFAULT_AWS_REGION = "eu-west-1"
DEFAULT_COST_MODE = "free-only"
VALID_COST_MODES = frozenset({"free-only", "allow-paid-with-confirmation"})


@dataclass(frozen=True)
class AWSConfig:
    """AWS region and optional shared-configuration profile name."""

    region: str = DEFAULT_AWS_REGION
    profile_name: str | None = None
    cost_mode: str = DEFAULT_COST_MODE

    @classmethod
    def from_sources(
        cls,
        *,
        region: str | None = None,
        profile_name: str | None = None,
        cost_mode: str | None = None,
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
        resolved_cost_mode = cost_mode or values.get("AWS_MCP_COST_MODE") or DEFAULT_COST_MODE
        if resolved_cost_mode not in VALID_COST_MODES:
            raise ValueError(
                "AWS_MCP_COST_MODE must be free-only or allow-paid-with-confirmation"
            )
        return cls(
            region=resolved_region,
            profile_name=resolved_profile,
            cost_mode=resolved_cost_mode,
        )
