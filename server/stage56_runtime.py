from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from server.continuous_data_sync_runtime import SyncJobRuntime, rollback_to_version
from server.notification_outbox_runtime import NotificationOutboxRuntime
from server.project_stage234_runtime import _owner as project_owner


EVIDENCE_GATES = {
    "remote_mcp_live",
    "latest_deploy_live_smoke",
    "chatgpt_native",
    "reviewer_live_login",
    "reviewer_demo_data_isolation",
    "exact_tool_allowlist",
    "public_policy_pages",
    "demo_video",
    "oauth_end_to_end",
}
EVIDENCE_DIGEST = re.compile(r"^[a-fA-F0-9]{32,128}$")


def _materialized_stage() -> int:
    try:
        payload = json.loads(Path("server/stage56_config.json").read_text(encoding="utf-8"))
        return max(1, min(6, int(payload.get("materialized_through_stage", 1))))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Stage56Runtime:
    def __init__(self) -> None:
        data_root = Path(os.getenv("APP_DATA_DIR", "data"))
        data_root.mkdir(parents=True, exist_ok=True)
        self.database_path = data_root / "stage56.sqlite3"
        self.published_database_path = data_root / "published-data.sqlite3"
        self.project_id = os.getenv("APP_PROJECT_ID", "generated-project")
        self.tenant_id = os.getenv("APP_TENANT_ID", f"tenant-{self.project_id}")
        self.source_id = os.getenv("DATA_SYNC_SOURCE_ID", "primary-source")
        self.jobs = SyncJobRuntime(self.database_path, max_attempts=3)
        ready_providers = {value.strip() for value in os.getenv("NOTIFICATION_READY_PROVIDERS", "").split(",") if value.strip()}
        self.notifications = NotificationOutboxRuntime(self.database_path, ready_providers=ready_providers)
        with self._connect() as connection:
            connection.executescript("""
            CREATE TABLE IF NOT EXISTS stage5_evidence(
              gate TEXT PRIMARY KEY, status TEXT NOT NULL, evidence_digest TEXT NOT NULL,
              environment TEXT NOT NULL, observed_at TEXT NOT NULL, recorded_by_hash TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stage56_audit(
              id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, actor_hash TEXT NOT NULL,
              detail_digest TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def admin(self, request: Request) -> dict | None:
        return project_owner(request)

    def record_evidence(self, payload: dict, principal: dict) -> dict:
        gate = str(payload.get("gate") or "")
        status = str(payload.get("status") or "").upper()
        digest = str(payload.get("evidence_digest") or "")
        environment = str(payload.get("environment") or "").lower()
        observed_at = str(payload.get("observed_at") or "")
        if gate not in EVIDENCE_GATES:
            return {"status": "invalid_gate"}
        if status not in {"PASS", "FAIL"}:
            return {"status": "invalid_status"}
        if not EVIDENCE_DIGEST.fullmatch(digest):
            return {"status": "invalid_evidence_digest"}
        if environment not in {"production", "chatgpt_native", "provider_review"} or not observed_at:
            return {"status": "invalid_evidence_context"}
        actor_hash = hashlib.sha256(str(principal["user_id"]).encode()).hexdigest()
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO stage5_evidence(gate,status,evidence_digest,environment,observed_at,recorded_by_hash,updated_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(gate) DO UPDATE SET status=excluded.status,evidence_digest=excluded.evidence_digest,"
                "environment=excluded.environment,observed_at=excluded.observed_at,recorded_by_hash=excluded.recorded_by_hash,updated_at=excluded.updated_at",
                (gate, status, digest.lower(), environment, observed_at, actor_hash, timestamp),
            )
            self._audit(connection, "stage5_evidence_recorded", actor_hash, {"gate": gate, "status": status})
        return {"status": "recorded", "gate": gate, "gate_status": status}

    def readiness(self) -> dict:
        required = set(EVIDENCE_GATES)
        if os.getenv("AUTH_REQUIRED", "false").lower() != "true":
            required.discard("oauth_end_to_end")
        with self._connect() as connection:
            rows = connection.execute("SELECT gate,status,environment,observed_at,updated_at FROM stage5_evidence").fetchall()
        evidence = {str(row["gate"]): {key: row[key] for key in ["status", "environment", "observed_at", "updated_at"]} for row in rows}
        missing = sorted(gate for gate in required if evidence.get(gate, {}).get("status") != "PASS")
        return {
            "status": "READY_FOR_OWNER_SUBMISSION" if not missing else "NOT_READY_FOR_SUBMISSION",
            "ready": not missing,
            "required_gates": sorted(required),
            "missing_or_failed": missing,
            "evidence": evidence,
            "owner_submit_still_required": True,
            "openai_approval_proven": False,
        }

    def contract(self) -> dict:
        path = Path("data_sync/sync-contract.json")
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        payload.update({"tenant_id": self.tenant_id, "project_id": self.project_id, "source_id": self.source_id})
        return payload

    def notify_operation(self, *, event_type: str, dedupe_key: str, payload: dict) -> dict:
        provider = os.getenv("NOTIFICATION_PROVIDER", "").strip()
        recipient_ref = os.getenv("NOTIFICATION_OWNER_RECIPIENT_REF", "").strip()
        if not provider or not recipient_ref:
            return {"status": "blocked", "reason": "notification_provider_or_recipient_not_configured"}
        return self.notifications.enqueue(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            recipient_ref=recipient_ref,
            event_type=event_type,
            channel=os.getenv("NOTIFICATION_CHANNEL", "email"),
            provider=provider,
            dedupe_key=dedupe_key,
            payload=payload,
            admin_canary=os.getenv("NOTIFICATION_ADMIN_CANARY", "false").lower() == "true",
            production_enabled=os.getenv("NOTIFICATION_PRODUCTION_ENABLED", "false").lower() == "true",
        )

    def _audit(self, connection: sqlite3.Connection, event_type: str, actor_hash: str, detail: dict) -> None:
        digest = hashlib.sha256(json.dumps(detail, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        connection.execute(
            "INSERT INTO stage56_audit(event_type,actor_hash,detail_digest,created_at) VALUES(?,?,?,?)",
            (event_type, actor_hash, digest, _now()),
        )


RUNTIME = Stage56Runtime()


def _forbidden() -> JSONResponse:
    return JSONResponse({"status": "owner_admin_required"}, status_code=403)


def _locked(required_stage: int) -> JSONResponse | None:
    if _materialized_stage() < required_stage:
        return JSONResponse({"status": "stage_not_entitled", "required_stage": required_stage}, status_code=403)
    return None


async def stage5_readiness(request: Request) -> JSONResponse:
    if locked := _locked(5):
        return locked
    if not RUNTIME.admin(request):
        return _forbidden()
    return JSONResponse(RUNTIME.readiness())


async def stage5_evidence(request: Request) -> JSONResponse:
    if locked := _locked(5):
        return locked
    principal = RUNTIME.admin(request)
    if not principal:
        return _forbidden()
    result = RUNTIME.record_evidence(await request.json(), principal)
    return JSONResponse(result, status_code=200 if result["status"] == "recorded" else 400)


async def stage6_status(request: Request) -> JSONResponse:
    if locked := _locked(6):
        return locked
    if not RUNTIME.admin(request):
        return _forbidden()
    return JSONResponse({
        "status": "ok",
        "jobs": RUNTIME.jobs.status(tenant_id=RUNTIME.tenant_id, project_id=RUNTIME.project_id, source_id=RUNTIME.source_id),
        "notifications": RUNTIME.notifications.scoped_status(tenant_id=RUNTIME.tenant_id, project_id=RUNTIME.project_id),
        "scheduler_authorized": os.getenv("STAGE6_SCHEDULER_ENABLED", "false").lower() == "true",
    })


async def stage6_enqueue(request: Request) -> JSONResponse:
    if locked := _locked(6):
        return locked
    if not RUNTIME.admin(request):
        return _forbidden()
    payload = await request.json()
    result = RUNTIME.jobs.enqueue(contract=RUNTIME.contract(), dedupe_key=str(payload.get("idempotency_key") or ""))
    return JSONResponse(result, status_code=200 if result["status"] in {"enqueued", "duplicate"} else 409)


async def stage6_run_once(request: Request) -> JSONResponse:
    if locked := _locked(6):
        return locked
    if not RUNTIME.admin(request):
        return _forbidden()
    if os.getenv("STAGE6_SCHEDULER_ENABLED", "false").lower() != "true":
        return JSONResponse({"status": "scheduler_not_authorized"}, status_code=503)
    source = Path(os.getenv("DATA_SYNC_SOURCE_DIR", ""))
    if not str(source) or not source.is_dir():
        return JSONResponse({"status": "source_not_configured"}, status_code=503)
    result = RUNTIME.jobs.run_next(contract=RUNTIME.contract(), source_dir=source, published_database_path=RUNTIME.published_database_path)
    if result.get("status") not in {"idle", "completed"}:
        result["notification"] = RUNTIME.notify_operation(
            event_type="stage6_sync_attention_required",
            dedupe_key=f"sync:{result.get('job_id', 'unknown')}:{result.get('status', 'unknown')}",
            payload={"job_id": result.get("job_id"), "status": result.get("status"), "attempts": result.get("attempts")},
        )
    return JSONResponse(result)


async def stage6_rollback(request: Request) -> JSONResponse:
    if locked := _locked(6):
        return locked
    principal = RUNTIME.admin(request)
    if not principal:
        return _forbidden()
    payload = await request.json()
    key = str(payload.get("idempotency_key") or "")
    if payload.get("confirmed") is not True or not key:
        return JSONResponse({"status": "confirmation_and_idempotency_required"}, status_code=409)
    try:
        version = int(payload.get("version"))
        result = rollback_to_version(
            database_path=RUNTIME.published_database_path,
            tenant_id=RUNTIME.tenant_id,
            project_id=RUNTIME.project_id,
            source_id=RUNTIME.source_id,
            version=version,
            idempotency_key=key,
            actor_hash=hashlib.sha256(str(principal["user_id"]).encode()).hexdigest(),
        )
    except (TypeError, ValueError) as exc:
        return JSONResponse({"status": "rollback_blocked", "reason": type(exc).__name__}, status_code=409)
    result["notification"] = RUNTIME.notify_operation(
        event_type="stage6_rollback",
        dedupe_key=f"rollback:{key}",
        payload={"status": result.get("status"), "version": result.get("version")},
    )
    return JSONResponse(result)
