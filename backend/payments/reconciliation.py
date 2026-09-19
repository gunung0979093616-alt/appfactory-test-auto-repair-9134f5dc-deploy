from __future__ import annotations


def summarize_reconciliation(orders: dict, grants: dict, *, tenant_id: str, project_id: str) -> dict:
    scoped_orders = [order for order in orders.values() if order.tenant_id == tenant_id and order.project_id == project_id]
    scoped_grants = [grant for grant in grants.values() if grant.get("tenant_id") == tenant_id and grant.get("project_id") == project_id]
    paid_orders = [order for order in scoped_orders if getattr(order, "status", "") == "paid"]
    rows = [{
        "order_id": order.order_id,
        "user_id": order.user_id,
        "product_code": order.product_code,
        "provider_transaction_id": order.provider_transaction_id,
        "payment_status": order.status,
        "fulfillment_status": "granted" if any(grant.get("order_id") == order.order_id and grant.get("status") == "active" for grant in scoped_grants) else "missing",
    } for order in scoped_orders]
    return {
        "owner_only": True,
        "paid_orders": len(paid_orders),
        "entitlement_grants": len(scoped_grants),
        "unmatched_paid_notify": max(0, len(paid_orders) - len(scoped_grants)),
        "tenant_id": tenant_id,
        "project_id": project_id,
        "rows": rows,
        "rule": "read-only report; no automatic refund, cancel, or entitlement extension",
    }
