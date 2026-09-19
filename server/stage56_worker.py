from __future__ import annotations

import os
from pathlib import Path

from server.stage56_runtime import RUNTIME


def run_once() -> dict:
    if os.getenv("STAGE6_SCHEDULER_ENABLED", "false").lower() != "true":
        return {"status": "scheduler_not_authorized"}
    source = Path(os.getenv("DATA_SYNC_SOURCE_DIR", ""))
    if not str(source) or not source.is_dir():
        return {"status": "source_not_configured"}
    result = RUNTIME.jobs.run_next(
        contract=RUNTIME.contract(),
        source_dir=source,
        published_database_path=RUNTIME.published_database_path,
    )
    if result.get("status") not in {"idle", "completed"}:
        result["notification"] = RUNTIME.notify_operation(
            event_type="stage6_sync_attention_required",
            dedupe_key=f"sync:{result.get('job_id', 'unknown')}:{result.get('status', 'unknown')}",
            payload={"job_id": result.get("job_id"), "status": result.get("status"), "attempts": result.get("attempts")},
        )
    return result


if __name__ == "__main__":
    print(run_once()["status"])
