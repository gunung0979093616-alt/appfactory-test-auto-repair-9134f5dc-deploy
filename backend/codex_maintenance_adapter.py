from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

SENSITIVE = {"password", "otp", "token", "cookie", "secret", "client_secret", "api_key", "hash_key", "hash_iv", "authorization", "raw_provider_payload"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS codex_project_connections (
  user_id TEXT NOT NULL, project_id TEXT NOT NULL, google_subject_hash TEXT NOT NULL,
  role TEXT NOT NULL, status TEXT NOT NULL, updated_at INTEGER NOT NULL,
  PRIMARY KEY(user_id, project_id)
);
CREATE TABLE IF NOT EXISTS codex_maintenance_jobs (
  job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, created_by_user_id TEXT NOT NULL, request_hash TEXT NOT NULL,
  stage_code TEXT NOT NULL, risk_level TEXT NOT NULL, status TEXT NOT NULL,
  result_summary TEXT NOT NULL DEFAULT '', evidence_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
"""

class ProjectCodexMaintenanceAdapter:
    def __init__(self, database_path: str | Path, project_id: str) -> None:
        self.database_path = Path(database_path)
        self.project_id = project_id
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(SCHEMA)

    def connect_verified_owner(self, *, user_id: str, google_sub: str, role: str, identity_verified: bool) -> dict[str, Any]:
        if not identity_verified or role != "owner_admin" or not user_id or not google_sub:
            raise PermissionError("verified Google owner_admin required")
        now = int(time.time())
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO codex_project_connections VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(user_id,project_id) DO UPDATE SET google_subject_hash=excluded.google_subject_hash,role=excluded.role,status='active',updated_at=excluded.updated_at",
                (user_id, self.project_id, _digest(google_sub), role, "active", now),
            )
        return {"status": "connected", "project_id": self.project_id, "manual_project_id_required": False}

    def local_status(self) -> dict[str, Any]:
        with sqlite3.connect(self.database_path) as connection:
            jobs = int(connection.execute(
                "SELECT COUNT(*) FROM codex_maintenance_jobs WHERE project_id=?", (self.project_id,)
            ).fetchone()[0])
        return {
            "status": "ready",
            "mode": "local_workspace",
            "project_id": self.project_id,
            "maintenance_jobs": jobs,
            "remote_mode": "waiting_for_project_stage3_oauth",
        }

    def create_local_job(self, request_text: str) -> dict[str, Any]:
        return self.create_job(
            user_id="local_workspace", identity_verified=True, role="owner_admin", request_text=request_text,
        ) | {"authority": "local_repository_access"}

    def record_local_result(self, *, job_id: str, status: str, summary: str, evidence: dict[str, Any]) -> dict[str, Any]:
        return self.record_result(
            user_id="local_workspace", identity_verified=True, role="owner_admin", job_id=job_id,
            status=status, summary=summary, evidence=evidence,
        ) | {"authority": "local_repository_access"}

    def masked_context(self, *, user_id: str, identity_verified: bool, role: str, business: dict[str, Any], technical: dict[str, Any]) -> dict[str, Any]:
        if not identity_verified or role != "owner_admin":
            raise PermissionError("verified project owner required")
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT job_id,stage_code,risk_level,status,result_summary,updated_at FROM codex_maintenance_jobs "
                "WHERE project_id=? AND created_by_user_id=? ORDER BY updated_at DESC LIMIT 20",
                (self.project_id, user_id),
            ).fetchall()
        return {"status": "ok", "project_id": self.project_id, "business": _clean(business), "technical": _clean(technical), "maintenance_jobs": [dict(row) for row in rows]}

    def create_job(self, *, user_id: str, identity_verified: bool, role: str, request_text: str) -> dict[str, Any]:
        if not identity_verified or role != "owner_admin":
            raise PermissionError("verified project owner required")
        request = (request_text or "").strip()
        if not request:
            raise ValueError("maintenance request required")
        stage_code, risk_level = _classify(request)
        job_id = f"maint_{secrets.token_hex(8)}"
        now = int(time.time())
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO codex_maintenance_jobs(job_id,project_id,created_by_user_id,request_hash,stage_code,risk_level,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (job_id, self.project_id, user_id, _digest(request), stage_code, risk_level, "queued", now, now),
            )
        return {"status": "queued", "job_id": job_id, "project_id": self.project_id, "stage_code": stage_code, "risk_level": risk_level, "request_content_stored": False}

    def record_result(self, *, user_id: str, identity_verified: bool, role: str, job_id: str, status: str, summary: str, evidence: dict[str, Any]) -> dict[str, Any]:
        if not identity_verified or role != "owner_admin":
            raise PermissionError("verified project owner required")
        allowed = {"diagnosed", "waiting_for_owner", "testing", "failed", "completed", "rolled_back"}
        if status not in allowed:
            raise ValueError("invalid result status")
        now = int(time.time())
        safe_summary = _redact(summary)[:1000]
        safe_evidence = _clean(evidence)
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT job_id FROM codex_maintenance_jobs WHERE job_id=? AND project_id=? AND created_by_user_id=?",
                (job_id, self.project_id, user_id),
            ).fetchone()
            if row is None:
                raise LookupError("maintenance job not found")
            connection.execute(
                "UPDATE codex_maintenance_jobs SET status=?,result_summary=?,evidence_json=?,updated_at=? WHERE job_id=?",
                (status, safe_summary, json.dumps(safe_evidence, ensure_ascii=False), now, job_id),
            )
        return {"status": status, "job_id": job_id, "project_id": self.project_id, "summary": safe_summary, "evidence": safe_evidence}

def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items() if key.lower() not in SENSITIVE}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, str):
        return _redact(value)
    return value

def _redact(value: str) -> str:
    import re
    text = str(value or "")
    return re.sub(r"(?i)(password|token|secret|api[_ -]?key|hash[_ -]?(?:key|iv)|authorization)\s*[:=]\s*\S+", r"=[REDACTED]", text)

def _classify(text: str) -> tuple[str, str]:
    lowered = text.lower()
    if any(term in lowered for term in ["付款", "訂閱", "權益", "額度", "payuni"]):
        return "stage_4_payment_entitlement", "high"
    if any(term in lowered for term in ["登入", "oauth", "google", "會員"]):
        return "stage_3_google_membership", "medium"
    if any(term in lowered for term in ["部署", "render", "回滾", "正式環境"]):
        return "stage_6_post_launch_data_operations", "high"
    if any(term in lowered for term in ["mcp", "外掛", "工具"]):
        return "stage_1_plugin_testable", "medium"
    if any(term in lowered for term in ["網站", "前端", "後端", "頁面"]):
        return "stage_2_industry_site", "medium"
    return "cross_stage", "medium"

def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
