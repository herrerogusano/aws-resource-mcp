"""Tests for non-sensitive AWS configuration."""

import pytest

from aws_resource_mcp.config import AWSConfig, DEFAULT_AWS_REGION


def test_default_region() -> None:
    config = AWSConfig.from_sources(environ={})
    assert config.region == DEFAULT_AWS_REGION == "eu-west-1"
    assert config.profile_name is None


def test_explicit_profile_and_region_take_precedence() -> None:
    config = AWSConfig.from_sources(
        region="eu-central-1",
        profile_name="requested-profile",
        environ={"AWS_REGION": "us-west-2", "AWS_PROFILE": "environment-profile"},
    )
    assert config.region == "eu-central-1"
    assert config.profile_name == "requested-profile"


def test_standard_environment_variables_are_supported() -> None:
    config = AWSConfig.from_sources(
        environ={"AWS_DEFAULT_REGION": "eu-north-1", "AWS_PROFILE": "test-profile"}
    )
    assert config.region == "eu-north-1"
    assert config.profile_name == "test-profile"


def test_cost_mode_defaults_to_free_only() -> None:
    assert AWSConfig.from_sources(environ={}).cost_mode == "free-only"


def test_cost_mode_can_require_confirmation_but_rejects_unsafe_values() -> None:
    assert AWSConfig.from_sources(
        environ={"AWS_MCP_COST_MODE": "allow-paid-with-confirmation"}
    ).cost_mode == "allow-paid-with-confirmation"
    with pytest.raises(ValueError):
        AWSConfig.from_sources(environ={"AWS_MCP_COST_MODE": "allow-all"})
