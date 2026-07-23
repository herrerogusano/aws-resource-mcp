"""Unit tests for the advanced health-check tool."""

from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from aws_resource_mcp.tools.health import health_check


def _session(*, credentials: object | None = object()) -> Mock:
    session = Mock()
    session.get_credentials.return_value = credentials
    sts = Mock()
    sts.get_caller_identity.return_value = {
        "Account": "111122223333",
        "Arn": "arn:aws:sts::111122223333:assumed-role/example/session-name",
        "UserId": "sensitive-user-id",
    }
    session.client.return_value = sts
    return session


@patch("aws_resource_mcp.tools.health.create_aws_session")
def test_health_check_without_arguments_checks_only_sts(create_session: Mock) -> None:
    session = _session()
    create_session.return_value = session

    result = health_check()

    assert result["status"] == "ok"
    assert result["server"] == {
        "status": "ok",
        "name": "aws-resource-mcp",
        "version": "0.1.0",
        "transport": "stdio",
    }
    assert result["aws"]["sts_accessible"] is True
    assert result["aws"]["account_id_masked"] == "********3333"
    assert result["aws"]["principal_type"] == "assumed-role"
    assert "session-name" not in str(result)
    assert session.client.call_args.args == ("sts",)


@patch("aws_resource_mcp.tools.health.create_aws_session")
def test_health_check_can_skip_aws(create_session: Mock) -> None:
    result = health_check(check_aws=False)

    assert result["status"] == "ok"
    assert result["aws"]["status"] == "not_checked"
    assert result["aws"]["check_requested"] is False
    create_session.assert_not_called()


@patch("aws_resource_mcp.tools.health.create_aws_session")
def test_health_check_degrades_without_credentials(create_session: Mock) -> None:
    create_session.return_value = _session(credentials=None)

    result = health_check()

    assert result["status"] == "degraded"
    assert result["server"]["status"] == "ok"
    assert result["aws"]["error"]["type"] == "credentials_not_found"
    create_session.return_value.client.assert_not_called()


@patch("aws_resource_mcp.tools.health.create_aws_session")
def test_health_check_degrades_when_sts_is_denied(create_session: Mock) -> None:
    session = _session()
    sts = session.client.return_value
    sts.get_caller_identity.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "sensitive"}},
        "GetCallerIdentity",
    )
    create_session.return_value = session

    result = health_check()

    assert result["status"] == "degraded"
    assert result["aws"]["status"] == "permission_denied"
    assert result["aws"]["error"]["type"] == "access_denied"
    assert "sensitive" not in str(result)


@patch("aws_resource_mcp.tools.health.AWSConfig.from_sources")
def test_health_check_reports_internal_configuration_error(from_sources: Mock) -> None:
    from_sources.side_effect = ValueError("secret configuration value")

    result = health_check(check_aws=False)

    assert result["status"] == "error"
    assert result["server"]["status"] == "error"
    assert "secret configuration value" not in str(result)


def test_health_check_reports_dynamic_capabilities_and_zero_cost() -> None:
    result = health_check(check_aws=False)

    assert result["capabilities"]["registered_adapter_count"] == 13
    assert result["capabilities"]["registered_tool_count"] == 7
    assert result["capabilities"]["registered_tools"] == [
        "health_check",
        "listar_recursos_aws",
        "analizar_actividad_recursos",
        "diagnosticar_cobertura_aws",
        "analizar_riesgo_costes",
        "revisar_free_tier",
        "consultar_costes_aws",
    ]
    assert result["capabilities"]["free_tier_api"]["cost_classification"] == "free"
    assert (
        result["capabilities"]["cost_explorer"]["cost_classification"]
        == "potentially_billable"
    )
    assert result["safety"] == {
        "cost_mode": "free-only",
        "billable_operations_executed": 0,
        "potentially_billable_operations_executed": 0,
        "potentially_billable_requests_executed": 0,
        "pending_consent_count": 0,
        "write_operations_enabled": False,
    }


def test_health_check_rejects_non_boolean_without_aws() -> None:
    result = health_check(check_aws="yes")  # type: ignore[arg-type]

    assert result["status"] == "error"
    assert result["safety"]["billable_operations_executed"] == 0
