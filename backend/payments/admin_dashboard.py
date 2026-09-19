from __future__ import annotations

from datetime import datetime, timezone


PURCHASE_TYPE_LABELS = {
    "one_time_purchase": "一次購買",
    "fixed_term_access": "固定期間使用",
    "prepaid_units": "固定次數／額度",
    "manual_renewal": "到期後自行續購",
}


def admin_payment_snapshot(orders: dict, grants: dict, *, tenant_id: str, project_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    rows = []
    for order in orders.values():
        if order.tenant_id != tenant_id or order.project_id != project_id:
            continue
        grant = next((item for item in grants.values() if item.get("tenant_id") == tenant_id and item.get("project_id") == project_id and item.get("order_id") == order.order_id), None)
        valid_until = grant.get("valid_until") if grant else None
        effective_status = grant.get("status") if grant else "not_granted"
        remaining_days = None
        if valid_until:
            delta = datetime.fromisoformat(valid_until) - now
            remaining_days = max(0, delta.days + (1 if delta.seconds else 0))
            if delta.total_seconds() <= 0 and effective_status == "active":
                effective_status = "expired"
        rows.append({
            "order_id": order.order_id,
            "user_id": order.user_id,
            "product_code": order.product_code,
            "purchase_type": PURCHASE_TYPE_LABELS.get(order.billing_model, order.billing_model),
            "payment_status": order.status,
            "purchased_at": order.paid_at,
            "access_starts_at": grant.get("valid_from") if grant else None,
            "access_expires_at": valid_until,
            "remaining_days": remaining_days,
            "units_granted": grant.get("units_granted") if grant else 0,
            "units_remaining": grant.get("units_remaining") if grant else 0,
            "entitlement_status": effective_status,
        })
    return {"owner_only": True, "tenant_id": tenant_id, "project_id": project_id, "rows": rows, "rule": "只讀顯示；退款、補權益與改到期日需要管理者另行確認並留下稽核紀錄。"}
