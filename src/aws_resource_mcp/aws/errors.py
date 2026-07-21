"""Safe error translation for AWS inventory operations."""

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    InvalidRegionError,
    NoCredentialsError,
    PartialCredentialsError,
    ProfileNotFound,
)

from aws_resource_mcp.models import InventoryError


class AWSInventoryGlobalError(RuntimeError):
    """Raised when inventory collection cannot establish its AWS identity."""

    def __init__(self, error: InventoryError) -> None:
        super().__init__(error["message"])
        self.error = error


def describe_aws_error(service: str, error: Exception) -> InventoryError:
    """Translate an SDK exception into a non-sensitive actionable error."""
    error_type = "aws_error"
    guidance = "Check the AWS configuration and try again."

    if isinstance(error, (NoCredentialsError, PartialCredentialsError)):
        error_type = "credentials_not_found"
        guidance = "Configure valid AWS credentials through the standard Boto3 credential chain."
    elif isinstance(error, ProfileNotFound):
        error_type = "profile_not_found"
        guidance = "Check that the selected AWS profile exists in the shared AWS configuration."
    elif isinstance(error, InvalidRegionError):
        error_type = "invalid_region"
        guidance = "Check that the AWS region name is valid."
    elif isinstance(error, EndpointConnectionError):
        error_type = "connection_error"
        guidance = "Check network access and the selected AWS region endpoint."
    elif isinstance(error, ClientError):
        code = str(error.response.get("Error", {}).get("Code", "Unknown"))
        if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
            error_type = "access_denied"
            guidance = f"Check the read-only IAM permissions required by {service}."
        elif code in {
            "ExpiredToken",
            "ExpiredTokenException",
            "InvalidClientTokenId",
            "SignatureDoesNotMatch",
            "UnrecognizedClientException",
        }:
            error_type = "invalid_credentials"
            guidance = "Refresh or correct the AWS credentials resolved by Boto3."
        else:
            error_type = code
    elif isinstance(error, BotoCoreError):
        error_type = type(error).__name__

    return {"service": service, "error_type": error_type, "message": guidance}
