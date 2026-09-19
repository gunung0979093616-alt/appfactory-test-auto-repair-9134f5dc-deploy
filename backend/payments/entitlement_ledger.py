from __future__ import annotations

from datetime import datetime


class EntitlementLedger:
    def __init__(self) -> None:
        self.grants: dict[str, dict] = {}

    def grant(self, *, tenant_id: str, project_id: str, order_id: str, user_id: str, product_code: str, billing_model: str, entitlement_kind: str, credits: int, valid_from: datetime, valid_until: datetime | None, idempotency_key: str) -> dict:
        scoped_key = f"{tenant_id}:{project_id}:{idempotency_key}"
        if scoped_key in self.grants:
            return self.grants[scoped_key]
        grant = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "order_id": order_id,
            "user_id": user_id,
            "product_code": product_code,
            "billing_model": billing_model,
            "entitlement_kind": entitlement_kind,
            "purchased_at": valid_from.isoformat(),
            "valid_from": valid_from.isoformat(),
            "valid_until": valid_until.isoformat() if valid_until else None,
            "units_granted": credits,
            "units_remaining": credits,
            "credits": credits,
            "source": "verified_notify",
            "idempotency_key": idempotency_key,
            "status": "active",
        }
        self.grants[scoped_key] = grant
        return grant

    def revoke_for_refund(self, *, tenant_id: str, project_id: str, order_id: str, product_code: str, refund_id: str) -> dict | None:
        for grant in self.grants.values():
            if grant["tenant_id"] == tenant_id and grant["project_id"] == project_id and grant["order_id"] == order_id and grant["product_code"] == product_code and grant["status"] == "active":
                grant["status"] = "revoked_refund"
                grant["refund_id"] = refund_id
                return grant
        return None
