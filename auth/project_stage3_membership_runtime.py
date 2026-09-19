from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from .project_stage_access_runtime import evaluate_stage_tool_access
except ImportError:
    from project_stage_access_runtime import evaluate_stage_tool_access


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL, google_sub TEXT NOT NULL, email TEXT NOT NULL, created_at INTEGER NOT NULL, UNIQUE(tenant_id,google_sub), UNIQUE(tenant_id,email));
CREATE TABLE IF NOT EXISTS project_memberships(user_id INTEGER NOT NULL, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, role TEXT NOT NULL, PRIMARY KEY(user_id,tenant_id,project_id));
CREATE TABLE IF NOT EXISTS sessions(session_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS project_stage_entitlements(user_id INTEGER NOT NULL, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, highest_stage INTEGER NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY(user_id,tenant_id,project_id));
"""


@dataclass(frozen=True)
class Stage3Config:
    google_client_id: str
    session_secret: str
    admin_emails: frozenset[str]
    database_path: Path
    test_mode: bool
    tenant_id: str
    project_id: str


def load_stage3_config() -> Stage3Config:
    return Stage3Config(
        google_client_id=os.environ.get("PROJECT_GOOGLE_CLIENT_ID", "").strip(),
        session_secret=os.environ.get("PROJECT_SESSION_SECRET", "").strip(),
        admin_emails=frozenset(x.strip().lower() for x in os.environ.get("PROJECT_ADMIN_EMAILS", "").split(",") if x.strip()),
        database_path=Path(os.environ.get("PROJECT_AUTH_DB_PATH", "runtime_data/project_membership.sqlite3")).expanduser(),
        test_mode=os.environ.get("PROJECT_AUTH_TEST_MODE", "").lower() == "true",
        tenant_id=os.environ.get("PROJECT_TENANT_ID", "").strip(),
        project_id=os.environ.get("PROJECT_ID", "").strip(),
    )


class Stage3MembershipRuntime:
    def __init__(self, config: Stage3Config | None = None) -> None:
        self.config = config or load_stage3_config()
        if not self.config.tenant_id or not self.config.project_id:
            raise ValueError("PROJECT_TENANT_ID and PROJECT_ID are required")
        self.config.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def _connect(self):
        connection = sqlite3.connect(self.config.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _verify_google_credential(self, credential: str) -> dict:
        if self.config.test_mode and credential.startswith("test:"):
            return json.loads(credential[5:])
        if not self.config.google_client_id:
            raise PermissionError("google_client_id_required")
        try:
            from google.auth.transport import requests
            from google.oauth2 import id_token
        except ImportError as exc:
            raise PermissionError("google_auth_dependency_required") from exc
        try:
            claims = id_token.verify_oauth2_token(credential, requests.Request(), self.config.google_client_id)
        except Exception as exc:
            raise PermissionError("invalid_google_credential") from exc
        if claims.get("email_verified") is not True:
            raise PermissionError("google_email_not_verified")
        return claims

    def login_with_google_credential(self, credential: str) -> dict:
        claims = self._verify_google_credential(credential)
        google_sub = str(claims.get("sub") or "").strip()
        email = str(claims.get("email") or "").strip().lower()
        if not google_sub or not email:
            raise ValueError("verified Google sub and email required")
        role = "owner_admin" if email in self.config.admin_emails else "member"
        now = int(time.time())
        with self._connect() as connection:
            conflict = connection.execute("SELECT google_sub FROM users WHERE tenant_id=? AND email=? AND google_sub<>?", (self.config.tenant_id,email,google_sub)).fetchone()
            if conflict:
                raise PermissionError("email_identity_conflict")
            connection.execute("INSERT INTO users(tenant_id,google_sub,email,created_at) VALUES(?,?,?,?) ON CONFLICT(tenant_id,google_sub) DO UPDATE SET email=excluded.email", (self.config.tenant_id,google_sub,email,now))
            user = connection.execute("SELECT id,email,google_sub FROM users WHERE tenant_id=? AND google_sub=?", (self.config.tenant_id,google_sub)).fetchone()
            existing = connection.execute("SELECT role FROM project_memberships WHERE user_id=? AND tenant_id=? AND project_id=?", (user["id"],self.config.tenant_id,self.config.project_id)).fetchone()
            effective_role = "owner_admin" if existing and existing["role"] == "owner_admin" else role
            connection.execute("INSERT INTO project_memberships(user_id,tenant_id,project_id,role) VALUES(?,?,?,?) ON CONFLICT(user_id,tenant_id,project_id) DO UPDATE SET role=excluded.role", (user["id"],self.config.tenant_id,self.config.project_id,effective_role))
            raw = secrets.token_urlsafe(32)
            digest = hmac.new(self.config.session_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
            connection.execute("INSERT INTO sessions(session_hash,user_id,tenant_id,project_id,expires_at) VALUES(?,?,?,?,?)", (digest,user["id"],self.config.tenant_id,self.config.project_id,now+1209600))
        return {"status":"ok","session":raw,"user":{"id":user["id"],"email":email,"google_sub":google_sub,"role":effective_role,"is_admin":effective_role=="owner_admin","tenant_id":self.config.tenant_id,"project_id":self.config.project_id}}

    def _current(self, session: str) -> dict | None:
        if not session:
            return None
        digest = hmac.new(self.config.session_secret.encode(), session.encode(), hashlib.sha256).hexdigest()
        with self._connect() as connection:
            row = connection.execute("SELECT u.id,u.email,u.google_sub,pm.role FROM sessions s JOIN users u ON u.id=s.user_id AND u.tenant_id=s.tenant_id JOIN project_memberships pm ON pm.user_id=u.id AND pm.tenant_id=s.tenant_id AND pm.project_id=s.project_id WHERE s.tenant_id=? AND s.project_id=? AND s.session_hash=? AND s.expires_at>?", (self.config.tenant_id,self.config.project_id,digest,int(time.time()))).fetchone()
        return dict(row) if row else None

    def current_user(self, session: str) -> dict | None:
        current = self._current(session)
        if not current:
            return None
        return {**current, "tenant_id": self.config.tenant_id, "project_id": self.config.project_id}

    def admin_summary(self, session: str) -> tuple[int, dict]:
        current = self._current(session)
        if not current:
            return 401, {"status":"login_required"}
        if current["role"] != "owner_admin":
            return 403, {"status":"admin_required"}
        return 200, {"status":"ok","project_id":self.config.project_id,"current_user":current}

    def authorize_stage_tool(self, user_id: int, tool_id: str, *, seeded_demo: bool = False) -> dict:
        with self._connect() as connection:
            membership = connection.execute("SELECT role FROM project_memberships WHERE user_id=? AND tenant_id=? AND project_id=?", (user_id,self.config.tenant_id,self.config.project_id)).fetchone()
            entitlement = connection.execute("SELECT highest_stage,status FROM project_stage_entitlements WHERE user_id=? AND tenant_id=? AND project_id=?", (user_id,self.config.tenant_id,self.config.project_id)).fetchone()
        if not membership:
            return {"allowed":False,"status":"PROJECT_MEMBERSHIP_REQUIRED"}
        highest = int(entitlement["highest_stage"]) if entitlement and entitlement["status"] == "active" else 0
        return evaluate_stage_tool_access(role=membership["role"], highest_stage=highest, tool_id=tool_id, seeded_demo=seeded_demo)
