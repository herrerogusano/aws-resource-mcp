"""Ephemeral, single-use consent records for bounded inventory completion."""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from threading import Lock
from typing import Any

from aws_resource_mcp.models import remove_sensitive_fields

DEFAULT_CONSENT_TTL_SECONDS = 300


class ConsentValidationError(RuntimeError):
    """A consent request cannot be used safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def identity_fingerprint(identity: dict[str, Any]) -> str:
    """Bind consent to an AWS identity without storing its identifiers."""
    material = "|".join(
        str(identity.get(key) or "") for key in ("account_id", "arn", "user_id")
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def scope_fingerprint(scope: dict[str, Any]) -> str:
    """Return a stable hash for filters that define an inventory request."""
    normalized = json.dumps(scope, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def anonymized_consent_id(consent_request_id: str) -> str:
    """Return a non-reversible identifier suitable for audit messages."""
    return hashlib.sha256(consent_request_id.encode("utf-8")).hexdigest()[:12]


def sanitize_provisional_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    """Store normalized inventory only, without identity or account identifiers."""
    value = deepcopy(inventory)
    value.pop("account", None)

    def strip_account_ids(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                key: strip_account_ids(child)
                for key, child in item.items()
                if str(key).lower() != "account_id"
            }
        if isinstance(item, list):
            return [strip_account_ids(child) for child in item]
        return item

    return remove_sensitive_fields(strip_account_ids(value))


@dataclass
class ConsentRecord:
    request_id: str
    created_at: datetime
    expires_at: datetime
    identity_hash: str
    scope: dict[str, Any]
    scope_hash: str
    pending_operations: list[dict[str, Any]]
    provisional_inventory: dict[str, Any]
    continuation_tokens: dict[str, str] = field(default_factory=dict)
    used: bool = False
    cancelled: bool = False


class InventoryConsentStore:
    """Short-lived process-local store; no credentials or raw AWS responses."""

    def __init__(self, ttl_seconds: int = DEFAULT_CONSENT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._records: dict[str, ConsentRecord] = {}
        self._audit_events: list[dict[str, Any]] = []
        self._lock = Lock()

    def create(
        self,
        *,
        identity_hash: str,
        scope: dict[str, Any],
        pending_operations: list[dict[str, Any]],
        provisional_inventory: dict[str, Any],
        continuation_tokens: dict[str, str] | None = None,
        now: datetime | None = None,
    ) -> ConsentRecord:
        timestamp = now or datetime.now(timezone.utc)
        record = ConsentRecord(
            request_id=secrets.token_urlsafe(24),
            created_at=timestamp,
            expires_at=timestamp + timedelta(seconds=self.ttl_seconds),
            identity_hash=identity_hash,
            scope=deepcopy(scope),
            scope_hash=scope_fingerprint(scope),
            pending_operations=deepcopy(pending_operations),
            provisional_inventory=sanitize_provisional_inventory(provisional_inventory),
            continuation_tokens=dict(continuation_tokens or {}),
        )
        with self._lock:
            self._records[record.request_id] = record
            self._audit_events.append(
                {
                    "consent_id": anonymized_consent_id(record.request_id),
                    "timestamp": timestamp.isoformat(),
                    "result": "created",
                    "operations": [
                        f"{item['service']}:{item['operation']}"
                        for item in pending_operations
                    ],
                    "requests_executed": 0,
                    "consumed": False,
                }
            )
        return record

    def get(
        self,
        request_id: str,
        *,
        now: datetime | None = None,
    ) -> ConsentRecord:
        timestamp = now or datetime.now(timezone.utc)
        with self._lock:
            record = self._records.get(request_id)
            if record is None:
                raise ConsentValidationError(
                    "consent_not_found",
                    "The consent request does not exist in this MCP process.",
                )
            if record.used:
                raise ConsentValidationError(
                    "consent_already_used",
                    "The consent request has already been consumed.",
                )
            if record.cancelled:
                raise ConsentValidationError(
                    "consent_cancelled",
                    "The consent request has been cancelled.",
                )
            if timestamp >= record.expires_at:
                raise ConsentValidationError(
                    "consent_expired",
                    "The consent request has expired.",
                )
            return record

    def consume(self, request_id: str) -> None:
        with self._lock:
            self._records[request_id].used = True
            self._audit_events.append(
                {
                    "consent_id": anonymized_consent_id(request_id),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "result": "consumed",
                    "requests_executed": 0,
                    "consumed": True,
                }
            )

    def cancel(self, request_id: str) -> ConsentRecord:
        record = self.get(request_id)
        with self._lock:
            record.cancelled = True
            self._audit_events.append(
                {
                    "consent_id": anonymized_consent_id(request_id),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "result": "cancelled",
                    "requests_executed": 0,
                    "consumed": False,
                }
            )
        return record

    def record_execution(self, request_id: str, authorization: Any) -> None:
        """Record only bounded operation metadata, never the full consent ID."""
        with self._lock:
            self._audit_events.append(
                {
                    "consent_id": anonymized_consent_id(request_id),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "result": "executed",
                    "operations": sorted(
                        f"{service}:{operation}"
                        for service, operation in authorization.operations_executed
                    ),
                    "requests_executed": authorization.requests_executed,
                    "pagination_requests_executed": (
                        authorization.pagination_requests_executed
                    ),
                    "regions": sorted(
                        {
                            event["region"]
                            for event in authorization.audit_events
                        }
                    ),
                    "consumed": True,
                }
            )

    def audit_events(self) -> list[dict[str, Any]]:
        """Return a copy of safe process-local audit metadata."""
        with self._lock:
            return deepcopy(self._audit_events)

    def pending_count(self, *, now: datetime | None = None) -> int:
        timestamp = now or datetime.now(timezone.utc)
        with self._lock:
            return sum(
                not record.used
                and not record.cancelled
                and timestamp < record.expires_at
                for record in self._records.values()
            )

    def clear(self) -> None:
        """Reset process-local state in tests."""
        with self._lock:
            self._records.clear()
            self._audit_events.clear()


CONSENT_STORE = InventoryConsentStore()


def consent_request_payload(record: ConsentRecord) -> dict[str, Any]:
    """Build the public request without exposing stored identity or tokens."""
    operations = [
        f"{item['service']}:{item['operation']}" for item in record.pending_operations
    ]
    services = list(
        dict.fromkeys(item["service"] for item in record.pending_operations)
    )
    regions = sorted(
        {
            region
            for item in record.pending_operations
            for region in item.get("regions", [])
        }
    )
    return {
        "consent_request_id": record.request_id,
        "purpose": "Complete the AWS resource inventory",
        "services": services,
        "operations": operations,
        "regions": regions,
        "estimated_max_requests": sum(
            item["estimated_max_requests"] for item in record.pending_operations
        ),
        "pagination_request_limit": sum(
            1 for item in record.pending_operations if item.get("continuation")
        ),
        "single_use": True,
        "expires_at": record.expires_at.isoformat(),
        "executed": False,
        "notice": (
            "These operations can be counted as service requests. Zero cost "
            "cannot be guaranteed because it depends on accumulated usage and "
            "the account conditions."
        ),
    }
