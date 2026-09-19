from __future__ import annotations

import hashlib
import sqlite3
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class UnverifiedIdentityError(ValueError):
    """Raised when caller-controlled claims are presented as trusted identity."""


ROLE_PERMISSIONS = {
    "user": {"project.read", "tool.call"},
    "developer": {"project.read", "project.write", "tool.call", "artifact.build"},
    "admin": {"project.read", "project.write", "tool.call", "artifact.build", "admin.audit.read"},
    "owner": {"project.read", "project.write", "tool.call", "artifact.build", "admin.audit.read", "member.manage"},
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS project_memberships (
  tenant_hash TEXT NOT NULL,
  project_hash TEXT NOT NULL,
  subject_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_hash, project_hash, subject_hash)
);
CREATE TABLE IF NOT EXISTS tool_usage_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_hash TEXT,
  project_hash TEXT,
  subject_hash TEXT,
  authenticated INTEGER NOT NULL,
  tool_name TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  request_size INTEGER NOT NULL,
  outcome TEXT NOT NULL,
  risk_code TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_usage_subject_risk
ON tool_usage_events(subject_hash, risk_code, created_at);
CREATE TABLE IF NOT EXISTS account_restrictions (
  subject_hash TEXT PRIMARY KEY,
  restriction_type TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_restrictions (
  tenant_hash TEXT NOT NULL,
  project_hash TEXT NOT NULL,
  subject_hash TEXT NOT NULL,
  restriction_type TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_hash, project_hash, subject_hash)
);
CREATE TABLE IF NOT EXISTS admin_action_audit_logs (
  audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_hash TEXT NOT NULL,
  project_hash TEXT NOT NULL,
  actor_hash TEXT NOT NULL,
  action TEXT NOT NULL,
  target_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS security_capability_state (
  tenant_hash TEXT NOT NULL,
  project_hash TEXT NOT NULL,
  subject_hash TEXT NOT NULL,
  capability_tags TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_hash, project_hash, subject_hash)
);
"""


@dataclass(frozen=True)
class VerifiedPrincipal:
    subject: str
    tenant_id: str
    roles: frozenset[str]

    @classmethod
    def from_server_claims(cls, claims: dict[str, Any], *, identity_verified: bool) -> "VerifiedPrincipal":
        if not identity_verified:
            raise UnverifiedIdentityError("identity must be verified by the server OAuth/session boundary")
        subject = str(claims.get("sub", "")).strip()
        tenant_id = str(claims.get("tenant_id", "")).strip()
        roles = frozenset(str(role).strip() for role in claims.get("roles", []) if str(role).strip() in ROLE_PERMISSIONS)
        if not subject or not tenant_id or not roles:
            raise UnverifiedIdentityError("verified claims require sub, tenant_id and at least one recognized role")
        return cls(subject=subject, tenant_id=tenant_id, roles=roles)


class IdentityRbacAbuseMonitor:
    """Tenant-scoped RBAC and privacy-safe security event persistence.

    Authentication is intentionally outside this class. Only a server OAuth or
    session verifier may create ``VerifiedPrincipal`` with
    ``identity_verified=True``. User text and MCP arguments are never identity.
    """

    def __init__(
        self,
        database_path: Path | str,
        *,
        verified_attempt_limit: int = 5,
        restriction_minutes: int = 15,
        capability_ttl_minutes: int = 30,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.verified_attempt_limit = max(1, verified_attempt_limit)
        self.restriction_minutes = max(1, restriction_minutes)
        self.capability_ttl_minutes = max(1, capability_ttl_minutes)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def upsert_project_membership(
        self,
        actor: VerifiedPrincipal,
        *,
        project_id: str,
        role: str,
        member: VerifiedPrincipal | None = None,
    ) -> None:
        member = member or actor
        if role not in ROLE_PERMISSIONS or actor.tenant_id != member.tenant_id:
            raise PermissionError("invalid role or cross-tenant membership")
        if member != actor and not self._has_permission(actor, "member.manage"):
            raise PermissionError("verified owner role required to manage members")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO project_memberships(tenant_hash,project_hash,subject_hash,role,created_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(tenant_hash,project_hash,subject_hash) DO UPDATE SET role=excluded.role",
                (_digest(actor.tenant_id), _digest(project_id), _digest(member.subject), role, now),
            )
            connection.execute(
                "INSERT INTO admin_action_audit_logs(tenant_hash,project_hash,actor_hash,action,target_hash,created_at) VALUES(?,?,?,?,?,?)",
                (_digest(actor.tenant_id), _digest(project_id), _digest(actor.subject), "membership.upsert", _digest(member.subject), now),
            )

    def authorize(self, principal: VerifiedPrincipal | None, *, permission: str, project_id: str) -> dict[str, Any]:
        if principal is None:
            return {"allowed": False, "reason": "verified_identity_required"}
        restriction = self.is_restricted(principal, project_id=project_id)
        if restriction["restricted"]:
            return {"allowed": False, "reason": "account_temporarily_restricted", **restriction}
        with self._connect() as connection:
            row = connection.execute(
                "SELECT role FROM project_memberships WHERE tenant_hash=? AND project_hash=? AND subject_hash=?",
                (_digest(principal.tenant_id), _digest(project_id), _digest(principal.subject)),
            ).fetchone()
        if row is None:
            return {"allowed": False, "reason": "project_membership_required"}
        role = str(row[0])
        allowed = permission in ROLE_PERMISSIONS.get(role, set()) and self._has_permission(principal, permission)
        return {"allowed": allowed, "reason": "allowed" if allowed else "permission_denied", "role": role}

    def record_tool_event(
        self,
        *,
        principal: VerifiedPrincipal | None,
        tool_name: str,
        request_text: str,
        outcome: str,
        risk_code: str = "none",
        project_id: str = "",
    ) -> dict[str, Any]:
        now = _utc_now()
        subject_hash = _digest(principal.subject) if principal else None
        tenant_hash = _digest(principal.tenant_id) if principal else None
        scoped_project_id = project_id or "developer-assistant-public"
        project_hash = _digest(scoped_project_id)
        request_bytes = (request_text or "").encode("utf-8")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO tool_usage_events(tenant_hash,project_hash,subject_hash,authenticated,tool_name,request_hash,request_size,outcome,risk_code,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    tenant_hash,
                    project_hash,
                    subject_hash,
                    int(principal is not None),
                    tool_name,
                    hashlib.sha256(request_bytes).hexdigest(),
                    len(request_bytes),
                    outcome[:128],
                    risk_code[:128],
                    now,
                ),
            )
            restriction = "none"
            restrictable_risk_codes = {
                "credential_theft",
                "covert_exfiltration",
                "malicious_persistence",
                "security_bypass",
                "cumulative_malicious_capability_chain",
                "secret_export_request",
                "owned_product_clone_request",
                "mother_system_internal_disclosure_request",
                "mother_repository_extraction_request",
            }
            if principal is not None and risk_code in restrictable_risk_codes:
                cutoff = (datetime.now(timezone.utc) - timedelta(minutes=self.restriction_minutes)).isoformat()
                count = int(connection.execute(
                    "SELECT COUNT(*) FROM tool_usage_events WHERE tenant_hash=? AND project_hash=? AND subject_hash=? "
                    "AND risk_code IN (?,?,?,?,?,?,?,?,?) AND created_at>=?",
                    (
                        tenant_hash,
                        project_hash,
                        subject_hash,
                        *sorted(restrictable_risk_codes),
                        cutoff,
                    ),
                ).fetchone()[0])
                if count >= self.verified_attempt_limit:
                    restriction = "temporary"
                    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=self.restriction_minutes)).isoformat()
                    connection.execute(
                        "INSERT INTO project_restrictions(tenant_hash,project_hash,subject_hash,restriction_type,reason_code,expires_at,created_at) "
                        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(tenant_hash,project_hash,subject_hash) DO UPDATE SET "
                        "restriction_type=excluded.restriction_type,reason_code=excluded.reason_code,expires_at=excluded.expires_at",
                        (tenant_hash, project_hash, subject_hash, restriction, "repeated_protected_requests", expires_at, now),
                    )
        return {
            "recorded": True,
            "authenticated": principal is not None,
            "restriction": restriction,
            "privacy": "request content is not stored; only digest, byte size and classified outcome are persisted",
        }

    def read_capability_tags(
        self,
        principal: VerifiedPrincipal | None,
        *,
        project_id: str,
        workflow_id: str = "default",
    ) -> list[str]:
        if principal is None or not project_id:
            return []
        with self._connect() as connection:
            row = connection.execute(
                "SELECT capability_tags,updated_at FROM security_capability_state WHERE tenant_hash=? AND project_hash=? AND subject_hash=?",
                (_digest(principal.tenant_id), _capability_project_hash(project_id, workflow_id), _digest(principal.subject)),
            ).fetchone()
        if row is None:
            return []
        updated_at = datetime.fromisoformat(str(row[1])) if len(row) > 1 else datetime.now(timezone.utc)
        if updated_at <= datetime.now(timezone.utc) - timedelta(minutes=self.capability_ttl_minutes):
            self.clear_capability_tags(principal, project_id=project_id, workflow_id=workflow_id)
            return []
        return sorted({tag for tag in str(row[0]).split(",") if tag})

    def merge_capability_tags(
        self,
        principal: VerifiedPrincipal | None,
        *,
        project_id: str,
        capability_tags: list[str],
        workflow_id: str = "default",
    ) -> list[str]:
        """Persist only classified tags for a verified subject; never raw prompts."""
        if principal is None or not project_id:
            return sorted(set(capability_tags))
        merged = sorted(
            set(self.read_capability_tags(principal, project_id=project_id, workflow_id=workflow_id))
            | set(capability_tags)
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO security_capability_state(tenant_hash,project_hash,subject_hash,capability_tags,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(tenant_hash,project_hash,subject_hash) DO UPDATE SET capability_tags=excluded.capability_tags,updated_at=excluded.updated_at",
                (
                    _digest(principal.tenant_id),
                    _capability_project_hash(project_id, workflow_id),
                    _digest(principal.subject),
                    ",".join(merged),
                    _utc_now(),
                ),
            )
        return merged

    def clear_capability_tags(
        self,
        principal: VerifiedPrincipal | None,
        *,
        project_id: str,
        workflow_id: str = "default",
    ) -> bool:
        """End one cumulative-analysis workflow without affecting another project or subject."""
        if principal is None or not project_id:
            return False
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM security_capability_state WHERE tenant_hash=? AND project_hash=? AND subject_hash=?",
                (
                    _digest(principal.tenant_id),
                    _capability_project_hash(project_id, workflow_id),
                    _digest(principal.subject),
                ),
            )
        return cursor.rowcount > 0

    def is_restricted(self, principal: VerifiedPrincipal | None, *, project_id: str = "developer-assistant-public") -> dict[str, Any]:
        if principal is None:
            return {"restricted": False, "reason": "anonymous_global_block_disabled"}
        with self._connect() as connection:
            row = connection.execute(
                "SELECT restriction_type,reason_code,expires_at FROM project_restrictions "
                "WHERE tenant_hash=? AND project_hash=? AND subject_hash=?",
                (_digest(principal.tenant_id), _digest(project_id or "developer-assistant-public"), _digest(principal.subject)),
            ).fetchone()
            if row is None:
                return {"restricted": False}
            if datetime.fromisoformat(str(row[2])) <= datetime.now(timezone.utc):
                connection.execute(
                    "DELETE FROM project_restrictions WHERE tenant_hash=? AND project_hash=? AND subject_hash=?",
                    (_digest(principal.tenant_id), _digest(project_id or "developer-assistant-public"), _digest(principal.subject)),
                )
                return {"restricted": False, "reason": "restriction_expired"}
        return {"restricted": True, "restriction_type": row[0], "reason": row[1], "expires_at": row[2]}

    def read_security_events(self, principal: VerifiedPrincipal, *, project_id: str) -> list[dict[str, Any]]:
        if not self.authorize(principal, permission="admin.audit.read", project_id=project_id)["allowed"]:
            return []
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT tool_name,outcome,risk_code,created_at FROM tool_usage_events "
                "WHERE tenant_hash=? AND project_hash=? ORDER BY event_id DESC LIMIT 100",
                (_digest(principal.tenant_id), _digest(project_id)),
            ).fetchall()
        return [dict(row) for row in rows]

    def _has_permission(self, principal: VerifiedPrincipal, permission: str) -> bool:
        return any(permission in ROLE_PERMISSIONS.get(role, set()) for role in principal.roles)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _capability_project_hash(project_id: str, workflow_id: str) -> str:
    return _digest(f"{project_id}:workflow:{workflow_id or 'default'}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_CURRENT_VERIFIED_PRINCIPAL: ContextVar[VerifiedPrincipal | None] = ContextVar(
    "appfactory_verified_principal",
    default=None,
)


def current_verified_principal() -> VerifiedPrincipal | None:
    return _CURRENT_VERIFIED_PRINCIPAL.get()


@contextmanager
def verified_principal_scope(principal: VerifiedPrincipal):
    """Internal bridge for a server-verified OAuth/session middleware."""
    token = _CURRENT_VERIFIED_PRINCIPAL.set(principal)
    try:
        yield
    finally:
        _CURRENT_VERIFIED_PRINCIPAL.reset(token)


def default_security_database_path() -> Path:
    configured = os.environ.get("APPFACTORY_SECURITY_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path("/tmp/ai-app-factory/security-events.sqlite3")
