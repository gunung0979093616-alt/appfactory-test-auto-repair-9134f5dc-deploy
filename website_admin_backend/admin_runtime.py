from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone


class AuthorizationError(PermissionError):
    pass


class UnsafeStatusError(ValueError):
    pass


class AdminRepository:
    def __init__(self, database_path: str = ":memory:") -> None:
        self.connection = sqlite3.connect(database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS site_pages (
          page_id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
          published INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_events (
          event_id INTEGER PRIMARY KEY AUTOINCREMENT, actor_subject TEXT NOT NULL,
          action TEXT NOT NULL, target TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS oauth_configuration_status (
          project_id TEXT PRIMARY KEY, configuration_fingerprint TEXT NOT NULL,
          lifecycle_status TEXT NOT NULL, last_verified_at TEXT,
          next_action TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """)

    def save_page(self, *, actor_subject: str, allowed_subjects: set[str], page_id: str, title: str, body: str, published: bool) -> dict:
        require_admin(actor_subject, allowed_subjects)
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            "INSERT INTO site_pages(page_id,title,body,published,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(page_id) DO UPDATE SET title=excluded.title,body=excluded.body,published=excluded.published,updated_at=excluded.updated_at",
            (page_id, title, body, int(published), now),
        )
        self.connection.execute(
            "INSERT INTO audit_events(actor_subject,action,target,created_at) VALUES(?,?,?,?)",
            (actor_subject, "site_page.save", page_id, now),
        )
        self.connection.commit()
        return dict(self.connection.execute("SELECT * FROM site_pages WHERE page_id=?", (page_id,)).fetchone())

    def save_oauth_status(self, *, actor_subject: str, allowed_subjects: set[str], payload: dict) -> dict:
        require_admin(actor_subject, allowed_subjects)
        allowed = {"project_id", "configuration_fingerprint", "lifecycle_status", "last_verified_at", "next_action"}
        forbidden = {"client_secret", "password", "otp", "cookie", "access_token", "refresh_token", "authorization_code"}
        keys = set(payload)
        if keys & forbidden or keys - allowed:
            raise UnsafeStatusError("OAuth admin status accepts sanitized allowlisted fields only")
        required = {"project_id", "configuration_fingerprint", "lifecycle_status", "next_action"}
        if not required.issubset(keys):
            raise UnsafeStatusError("missing required OAuth status fields")
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            "INSERT INTO oauth_configuration_status(project_id,configuration_fingerprint,lifecycle_status,last_verified_at,next_action,updated_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET configuration_fingerprint=excluded.configuration_fingerprint,"
            "lifecycle_status=excluded.lifecycle_status,last_verified_at=excluded.last_verified_at,next_action=excluded.next_action,updated_at=excluded.updated_at",
            (payload["project_id"], payload["configuration_fingerprint"], payload["lifecycle_status"], payload.get("last_verified_at"), payload["next_action"], now),
        )
        self.connection.execute(
            "INSERT INTO audit_events(actor_subject,action,target,created_at) VALUES(?,?,?,?)",
            (actor_subject, "oauth_configuration_status.save", payload["project_id"], now),
        )
        self.connection.commit()
        return self.get_oauth_status(actor_subject=actor_subject, allowed_subjects=allowed_subjects, project_id=payload["project_id"])

    def get_oauth_status(self, *, actor_subject: str, allowed_subjects: set[str], project_id: str) -> dict:
        require_admin(actor_subject, allowed_subjects)
        row = self.connection.execute("SELECT * FROM oauth_configuration_status WHERE project_id=?", (project_id,)).fetchone()
        return dict(row) if row else {}

    def audit_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])


def require_admin(subject: str, allowed_subjects: set[str]) -> None:
    if not subject or subject not in allowed_subjects:
        raise AuthorizationError("verified owner-admin session required")


def self_test() -> dict:
    repository = AdminRepository()
    unauthorized = False
    try:
        repository.save_page(actor_subject="visitor", allowed_subjects={"owner"}, page_id="home", title="x", body="x", published=False)
    except AuthorizationError:
        unauthorized = True
    row = repository.save_page(actor_subject="owner", allowed_subjects={"owner"}, page_id="home", title="首頁", body="公開內容", published=True)
    oauth_unauthorized = False
    try:
        repository.get_oauth_status(actor_subject="visitor", allowed_subjects={"owner"}, project_id="demo")
    except AuthorizationError:
        oauth_unauthorized = True
    oauth_row = repository.save_oauth_status(
        actor_subject="owner",
        allowed_subjects={"owner"},
        payload={
            "project_id": "demo",
            "configuration_fingerprint": "sha256-demo",
            "lifecycle_status": "CONFIGURED",
            "last_verified_at": "2026-09-06T00:00:00+00:00",
            "next_action": "verify deployed callback",
        },
    )
    secret_rejected = False
    try:
        repository.save_oauth_status(
            actor_subject="owner",
            allowed_subjects={"owner"},
            payload={"project_id": "demo", "client_secret": "must-not-store"},
        )
    except UnsafeStatusError:
        secret_rejected = True
    checks = {
        "unauthorized_write_rejected": unauthorized,
        "authorized_write_persisted": row["title"] == "首頁" and row["published"] == 1,
        "oauth_unauthorized_read_rejected": oauth_unauthorized,
        "oauth_safe_status_persisted": oauth_row["configuration_fingerprint"] == "sha256-demo",
        "oauth_secret_field_rejected": secret_rejected,
        "audit_event_recorded": repository.audit_count() == 2,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "truth_boundary": "Local SQLite runtime self-test only; Google OAuth and deployed admin proof remain separate."}


if __name__ == "__main__" and "--self-test" in sys.argv:
    result = self_test()
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
