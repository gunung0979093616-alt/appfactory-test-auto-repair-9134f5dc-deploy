from __future__ import annotations

from datetime import datetime, timezone


def _effective_status(grant: dict, now: datetime) -> str:
    if grant.get("status") != "active":
        return str(grant.get("status") or "unknown")
    valid_until = grant.get("valid_until")
    if valid_until and datetime.fromisoformat(valid_until) <= now:
        return "expired"
    return "active"


def account_snapshot(user_id: str, orders: dict, grants: dict, *, tenant_id: str, project_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    user_orders = [order.__dict__ for order in orders.values() if order.user_id == user_id and order.tenant_id == tenant_id and order.project_id == project_id]
    user_grants = [dict(grant, effective_status=_effective_status(grant, now)) for grant in grants.values() if grant["user_id"] == user_id and grant["tenant_id"] == tenant_id and grant["project_id"] == project_id]
    return {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "user_id": user_id,
        "orders": user_orders,
        "entitlements": user_grants,
        "rule": "authenticated user records only",
    }
