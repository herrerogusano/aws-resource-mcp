"""Tests for STS caller identity normalization and failures."""

from unittest.mock import Mock

from botocore.exceptions import ClientError, NoCredentialsError
import pytest

from aws_resource_mcp.aws.identity import get_aws_identity


def test_get_aws_identity_normalizes_response() -> None:
    client = Mock()
    client.get_caller_identity.return_value = {
        "Account": "111122223333",
        "Arn": "arn:aws:iam::111122223333:user/example",
        "UserId": "EXAMPLEUSERID",
    }
    session = Mock()
    session.client.return_value = client

    assert get_aws_identity(session) == {
        "account_id": "111122223333",
        "arn": "arn:aws:iam::111122223333:user/example",
        "user_id": "EXAMPLEUSERID",
    }


@pytest.mark.parametrize(
    "error",
    [
        NoCredentialsError(),
        ClientError(
            {"Error": {"Code": "ExpiredToken", "Message": "expired"}},
            "GetCallerIdentity",
        ),
    ],
)
def test_get_aws_identity_propagates_credential_errors(error: Exception) -> None:
    client = Mock()
    client.get_caller_identity.side_effect = error
    session = Mock()
    session.client.return_value = client

    with pytest.raises(type(error)):
        get_aws_identity(session)
