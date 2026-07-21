"""Non-sensitive runtime configuration for AWS access."""

from dataclasses import dataclass
import os
from typing import Mapping

DEFAULT_AWS_REGION = "eu-west-1"


@dataclass(frozen=True)
class AWSConfig:
    """AWS region and optional shared-configuration profile name."""

    region: str = DEFAULT_AWS_REGION
    profile_name: str | None = None

    @classmethod
    def from_sources(
        cls,
        *,
        region: str | None = None,
        profile_name: str | None = None,
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
        return cls(region=resolved_region, profile_name=resolved_profile)
