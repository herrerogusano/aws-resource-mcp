"""Tests for Boto3 session construction."""

from unittest.mock import Mock

from aws_resource_mcp.aws.session import create_aws_session


def test_session_without_profile() -> None:
    factory = Mock(return_value=object())
    session = create_aws_session(session_factory=factory)
    assert session is factory.return_value
    factory.assert_called_once_with(region_name="eu-west-1")


def test_session_with_optional_profile() -> None:
    factory = Mock(return_value=object())
    create_aws_session("eu-central-1", "test-profile", session_factory=factory)
    factory.assert_called_once_with(
        region_name="eu-central-1", profile_name="test-profile"
    )
