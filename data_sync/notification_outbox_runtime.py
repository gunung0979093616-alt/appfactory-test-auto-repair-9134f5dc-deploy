from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS notification_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_hash TEXT NOT NULL,
  project_hash TEXT NOT NULL,
  recipient_ref_hash TEXT NOT NULL,
  event_type TEXT NOT NULL,
  channel TEXT NOT NULL,
  provider TEXT NOT NULL,
  dedupe_key TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  state TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL,
  last_error_code TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(tenant_hash, project_hash, channel, dedupe_key)
);
CREATE INDEX IF NOT EXISTS idx_notification_outbox_claim
ON notification_outbox(provider, state, next_attempt_at);
CREATE TABLE IF NOT EXISTS notification_delivery_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  outbox_id INTEGER NOT NULL,
  event TEXT NOT NULL,
  detail_code TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class NotificationOutboxRuntime:
    """Privacy-safe, tenant-isolated notification delivery state machine.

    The database stores recipient references and payload digests only. A provider
    adapter must resolve the recipient and message at delivery time from the
    owning project's protected data store.
    """

    def __init__(
        self,
        database_path: Path | str,
        *,
        ready_providers: set[str] | None = None,
        daily_limit: int = 100,
        monthly_limit: int = 1000,
        max_attempts: int = 5,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.ready_providers = ready_providers or set()
        self.daily_limit = max(1, daily_limit)
        self.monthly_limit = max(1, monthly_limit)
        self.max_attempts = max(1, max_attempts)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def enqueue(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recipient_ref: str,
        event_type: str,
        channel: str,
        provider: str,
        dedupe_key: str,
        payload: dict[str, Any],
        admin_canary: bool = False,
        production_enabled: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if provider not in self.ready_providers:
            return {"status": "blocked", "reason": "provider_not_ready"}
        if production_enabled is False and admin_canary is False:
            return {"status": "blocked", "reason": "admin_canary_required_before_production"}
        if not all(str(value).strip() for value in [tenant_id, project_id, recipient_ref, event_type, channel, dedupe_key]):
            return {"status": "blocked", "reason": "missing_required_scope"}
        current = now or datetime.now(timezone.utc)
        tenant_hash = _digest(tenant_id)
        project_hash = _digest(project_id)
        if self._sent_count(tenant_hash, provider, current, monthly=False) >= self.daily_limit:
            return {"status": "blocked", "reason": "daily_quota_exceeded"}
        if self._sent_count(tenant_hash, provider, current, monthly=True) >= self.monthly_limit:
            return {"status": "blocked", "reason": "monthly_quota_exceeded"}
        timestamp = current.isoformat()
        values = (
            tenant_hash,
            project_hash,
            _digest(recipient_ref),
            event_type,
            channel,
            provider,
            dedupe_key,
            _payload_digest(payload),
            "pending",
            timestamp,
            timestamp,
            timestamp,
        )
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO notification_outbox(tenant_hash,project_hash,recipient_ref_hash,event_type,channel,provider,dedupe_key,payload_digest,state,next_attempt_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    values,
                )
                outbox_id = int(cursor.lastrowid)
                self._event(connection, outbox_id, "enqueued", "admin_canary" if admin_canary else "production", timestamp)
            return {"status": "enqueued", "outbox_id": outbox_id}
        except sqlite3.IntegrityError:
            return {"status": "duplicate", "reason": "dedupe_key_already_exists"}

    def claim_batch(self, *, provider: str, limit: int = 20, now: datetime | None = None) -> list[dict[str, Any]]:
        if provider not in self.ready_providers:
            return []
        timestamp = (now or datetime.now(timezone.utc)).isoformat()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT id,tenant_hash,project_hash,recipient_ref_hash,event_type,channel,provider,payload_digest,attempts "
                "FROM notification_outbox WHERE provider=? AND state IN ('pending','retry') AND next_attempt_at<=? "
                "ORDER BY id LIMIT ?",
                (provider, timestamp, max(1, limit)),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids:
                changed = connection.executemany(
                    "UPDATE notification_outbox SET state='sending',attempts=attempts+1,updated_at=? WHERE id=? AND state IN ('pending','retry')",
                    [(timestamp, outbox_id) for outbox_id in ids],
                )
                del changed
            connection.commit()
            claimed = connection.execute(
                "SELECT id,tenant_hash,project_hash,recipient_ref_hash,event_type,channel,provider,payload_digest,attempts "
                f"FROM notification_outbox WHERE id IN ({','.join('?' for _ in ids)}) AND state='sending' ORDER BY id",
                ids,
            ).fetchall() if ids else []
        return [dict(row) for row in claimed]

    def recover_stale_claims(self, *, older_than: datetime, now: datetime | None = None) -> dict[str, Any]:
        """Return abandoned sending leases to retry without exposing payloads."""
        timestamp = (now or datetime.now(timezone.utc)).isoformat()
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE notification_outbox SET state='retry',next_attempt_at=?,last_error_code='worker_lease_expired',updated_at=? "
                "WHERE state='sending' AND updated_at<?",
                (timestamp, timestamp, older_than.isoformat()),
            ).rowcount
        return {"status": "recovered", "count": int(changed)}

    def scoped_status(self, *, tenant_id: str, project_id: str) -> dict[str, Any]:
        tenant_hash = _digest(tenant_id)
        project_hash = _digest(project_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT state,COUNT(*) FROM notification_outbox WHERE tenant_hash=? AND project_hash=? GROUP BY state",
                (tenant_hash, project_hash),
            ).fetchall()
        return {"status": "ok", "counts": {str(state): int(count) for state, count in rows}}

    def mark_sent(self, outbox_id: int, *, now: datetime | None = None) -> dict[str, str]:
        timestamp = (now or datetime.now(timezone.utc)).isoformat()
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE notification_outbox SET state='sent',updated_at=?,last_error_code='' WHERE id=? AND state='sending'",
                (timestamp, outbox_id),
            ).rowcount
            if changed:
                self._event(connection, outbox_id, "sent", "provider_accepted", timestamp)
        return {"status": "sent" if changed else "ignored", "reason": "" if changed else "not_in_sending_state"}

    def mark_failed(self, outbox_id: int, *, error_code: str, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        with self._connect() as connection:
            row = connection.execute("SELECT attempts,state FROM notification_outbox WHERE id=?", (outbox_id,)).fetchone()
            if row is None or row[1] != "sending":
                return {"status": "ignored", "reason": "not_in_sending_state"}
            attempts = int(row[0])
            state = "dead_letter" if attempts >= self.max_attempts else "retry"
            delay_minutes = min(60, 2 ** max(0, attempts - 1))
            next_attempt = (current + timedelta(minutes=delay_minutes)).isoformat()
            connection.execute(
                "UPDATE notification_outbox SET state=?,next_attempt_at=?,last_error_code=?,updated_at=? WHERE id=?",
                (state, next_attempt, _safe_code(error_code), current.isoformat(), outbox_id),
            )
            self._event(connection, outbox_id, state, _safe_code(error_code), current.isoformat())
        return {"status": state, "attempts": attempts, "next_attempt_at": next_attempt}

    def campaign_status(
        self,
        *,
        tenant_id: str,
        project_id: str,
        event_type: str,
        expected_targets: int,
    ) -> dict[str, Any]:
        """Return a deterministic auto-stop decision without sending anything."""
        tenant_hash = _digest(tenant_id)
        project_hash = _digest(project_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT state, COUNT(*) FROM notification_outbox "
                "WHERE tenant_hash=? AND project_hash=? AND event_type=? GROUP BY state",
                (tenant_hash, project_hash, event_type),
            ).fetchall()
        counts = {str(state): int(count) for state, count in rows}
        terminal = counts.get("sent", 0) + counts.get("dead_letter", 0)
        active = counts.get("pending", 0) + counts.get("retry", 0) + counts.get("sending", 0)
        observed = terminal + active
        if expected_targets < 0:
            return {"status": "blocked", "reason": "invalid_expected_targets", "auto_stop": False, "counts": counts}
        if observed > expected_targets:
            return {"status": "mismatch", "reason": "observed_targets_exceed_expected", "auto_stop": False, "counts": counts}
        complete = observed == expected_targets and active == 0
        return {
            "status": "completed" if complete else "active",
            "auto_stop": complete,
            "expected_targets": expected_targets,
            "observed_targets": observed,
            "terminal_targets": terminal,
            "active_targets": active,
            "counts": counts,
        }

    def _sent_count(self, tenant_hash: str, provider: str, now: datetime, *, monthly: bool) -> int:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) if monthly else now.replace(hour=0, minute=0, second=0, microsecond=0)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM notification_outbox WHERE tenant_hash=? AND provider=? AND state='sent' AND updated_at>=?",
                (tenant_hash, provider, start.isoformat()),
            ).fetchone()
        return int(row[0])

    @staticmethod
    def _event(connection: sqlite3.Connection, outbox_id: int, event: str, detail: str, timestamp: str) -> None:
        connection.execute(
            "INSERT INTO notification_delivery_events(outbox_id,event,detail_code,created_at) VALUES(?,?,?,?)",
            (outbox_id, event, detail, timestamp),
        )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_digest(payload: dict[str, Any]) -> str:
    return _digest(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _safe_code(value: str) -> str:
    cleaned = "".join(character for character in value if character.isalnum() or character in {"_", "-"})
    return cleaned[:80] or "provider_error"
