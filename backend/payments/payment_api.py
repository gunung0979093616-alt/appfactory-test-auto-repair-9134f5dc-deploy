from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from typing import Any
from uuid import uuid4

from .entitlement_ledger import EntitlementLedger
from .payuni_adapter import PayuniAdapter


PUBLIC_CHECKOUT_ENABLED = os.getenv("PUBLIC_CHECKOUT_ENABLED", "false").lower() == "true"
PAYMENT_ACCEPTANCE_KILL_SWITCH = os.getenv("PAYMENT_ACCEPTANCE_KILL_SWITCH", "false").lower() == "true"
ENTITLEMENT_FULFILLMENT_KILL_SWITCH = os.getenv("ENTITLEMENT_FULFILLMENT_KILL_SWITCH", "false").lower() == "true"
PROJECT_TENANT_ID = 'tenant-7ba985c9fe58e09b'
PROJECT_ID = 'auto-repair-plugin-9134f5dc'


GENERATED_PLANS = {'starter': {'product_code': 'starter', 'billing_model': 'one_time_purchase', 'lifecycle_status': 'draft', 'amount': None, 'days': None, 'credits': None, 'entitlement_kind': 'project_feature_access', 'ready': False, 'plan_version': None, 'confirmed_at': None}, 'professional': {'product_code': 'professional', 'billing_model': 'one_time_purchase', 'lifecycle_status': 'draft', 'amount': None, 'days': None, 'credits': None, 'entitlement_kind': 'project_feature_access', 'ready': False, 'plan_version': None, 'confirmed_at': None}, 'business': {'product_code': 'business', 'billing_model': 'one_time_purchase', 'lifecycle_status': 'draft', 'amount': None, 'days': None, 'credits': None, 'entitlement_kind': 'project_feature_access', 'ready': False, 'plan_version': None, 'confirmed_at': None}}


@dataclass
class PaymentOrder:
    tenant_id: str
    project_id: str
    order_id: str
    user_id: str
    product_code: str
    billing_model: str
    plan_version: str
    amount: int
    entitlement_kind: str
    credits: int
    valid_days: int | None
    status: str
    created_at: str
    paid_at: str | None = None
    provider_transaction_id: str | None = None


class PaymentApi:
    # The generated scaffold is process-local until a durable adapter explicitly
    # replaces it.  The main HTTP integration checks this before production use.
    durable_storage = False

    def __init__(self, adapter: PayuniAdapter | None = None, ledger: EntitlementLedger | None = None, plans: dict | None = None, *, tenant_id: str = PROJECT_TENANT_ID, project_id: str = PROJECT_ID) -> None:
        if not tenant_id or not project_id:
            raise ValueError("tenant_id_and_project_id_required")
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.adapter = adapter or PayuniAdapter()
        self.ledger = ledger or EntitlementLedger()
        self.orders: dict[str, PaymentOrder] = {}
        self.processed_notify_ids: set[str] = set()
        self.processed_refund_ids: set[str] = set()
        source_plans = GENERATED_PLANS if plans is None else plans
        self.plans = {code: dict(plan, product_code=code) for code, plan in source_plans.items()}
        self.plan_history: dict[str, list[dict]] = {code: [dict(plan)] for code, plan in self.plans.items()}

    def register_plan_version(self, product_code: str, plan: dict) -> dict[str, Any]:
        if plan.get("product_code") not in {None, product_code}:
            return {"status": "blocked", "reason": "product_code_is_immutable"}
        candidate = dict(plan, product_code=product_code)
        version = str(candidate.get("plan_version") or "")
        if not version:
            return {"status": "blocked", "reason": "plan_version_required"}
        if any(str(item.get("plan_version")) == version for item in self.plan_history.get(product_code, [])):
            return {"status": "blocked", "reason": "plan_version_already_exists"}
        self.plan_history.setdefault(product_code, []).append(dict(candidate))
        self.plans[product_code] = candidate
        return {"status": "registered", "product_code": product_code, "plan_version": version}

    def rollback_plan_version(self, product_code: str, plan_version: str) -> dict[str, Any]:
        snapshot = next((item for item in self.plan_history.get(product_code, []) if str(item.get("plan_version")) == plan_version), None)
        if snapshot is None:
            return {"status": "blocked", "reason": "unknown_plan_version"}
        self.plans[product_code] = dict(snapshot)
        return {"status": "rolled_back", "product_code": product_code, "plan_version": plan_version, "history_preserved": True}

    def create_order(self, user_id: str, product_code: str, *, surface: str = "desktop", sandbox: bool = True) -> dict[str, Any]:
        if PAYMENT_ACCEPTANCE_KILL_SWITCH:
            return {"status": "blocked", "reason": "payment_acceptance_kill_switch"}
        if not sandbox and not PUBLIC_CHECKOUT_ENABLED:
            return {"status": "blocked", "reason": "PUBLIC_CHECKOUT_ENABLED=false"}
        if surface not in {"desktop", "mobile"}:
            return {"status": "blocked", "reason": "unsupported_checkout_surface"}
        if product_code not in self.plans:
            return {"status": "blocked", "reason": "unknown_plan"}
        plan = self.plans[product_code]
        if plan.get("lifecycle_status") != "active" or not plan.get("ready"):
            return {"status": "blocked", "reason": "plan_not_confirmed"}
        order = PaymentOrder(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            order_id=f"ord_{uuid4().hex[:16]}",
            user_id=user_id,
            product_code=product_code,
            billing_model=str(plan.get("billing_model") or "one_time_purchase"),
            plan_version=str(plan["plan_version"]),
            amount=plan["amount"],
            entitlement_kind=str(plan["entitlement_kind"]),
            credits=int(plan.get("credits") or 0),
            valid_days=int(plan["days"]) if plan.get("days") is not None else None,
            status="pending_payment",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        try:
            payment_entry = self.adapter.build_upp_entry(order.__dict__)
        except (RuntimeError, ValueError) as exc:
            return {"status": "blocked", "reason": str(exc)}
        self.orders[order.order_id] = order
        return {"status": "pending_payment", "order_id": order.order_id, "payment_entry": payment_entry}

    def handle_notify(self, payload: dict[str, Any]) -> dict[str, Any]:
        parsed = self.adapter.verify_notify(payload)
        if parsed["status"] != "verified":
            return {"status": "rejected", "reason": parsed["reason"]}
        return self._settle_verified_payment(parsed)

    def handle_trade_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        parsed = self.adapter.verify_trade_query(payload)
        if parsed["status"] != "verified":
            return {"status": "rejected", "reason": parsed["reason"]}
        return self._settle_verified_payment(parsed)

    def _settle_verified_payment(self, parsed: dict[str, Any]) -> dict[str, Any]:
        transaction_id = parsed["transaction_id"]
        if transaction_id in self.processed_notify_ids:
            return {"status": "ignored_duplicate", "transaction_id": transaction_id}
        order = self.orders.get(parsed["order_id"])
        if not order:
            return {"status": "rejected", "reason": "unknown_order"}
        if order.tenant_id != self.tenant_id or order.project_id != self.project_id:
            return {"status": "rejected", "reason": "cross_project_order"}
        if parsed.get("tenant_id") not in {None, "", order.tenant_id} or parsed.get("project_id") not in {None, "", order.project_id}:
            return {"status": "rejected", "reason": "cross_project_callback"}
        if parsed["amount"] != order.amount:
            return {"status": "rejected", "reason": "amount_mismatch"}
        if parsed.get("product_code") and parsed["product_code"] != order.product_code:
            return {"status": "rejected", "reason": "product_code_mismatch"}
        if order.provider_transaction_id not in {None, transaction_id}:
            return {"status": "rejected", "reason": "provider_transaction_mismatch"}
        order.provider_transaction_id = transaction_id
        if ENTITLEMENT_FULFILLMENT_KILL_SWITCH:
            order.status = "paid_pending_fulfillment"
            return {"status": "queued_reconciliation", "order_id": order.order_id, "transaction_id": transaction_id}
        paid_at = datetime.now(timezone.utc)
        order.status = "paid"
        order.paid_at = paid_at.isoformat()
        self.processed_notify_ids.add(transaction_id)
        valid_until = paid_at + timedelta(days=order.valid_days) if order.valid_days is not None else None
        grant = self.ledger.grant(tenant_id=order.tenant_id, project_id=order.project_id, order_id=order.order_id, user_id=order.user_id, product_code=order.product_code, billing_model=order.billing_model, entitlement_kind=order.entitlement_kind, credits=order.credits, valid_from=paid_at, valid_until=valid_until, idempotency_key=transaction_id)
        return {"status": "paid", "order_id": order.order_id, "entitlement": grant}

    def handle_refund(self, payload: dict[str, Any]) -> dict[str, Any]:
        parsed = self.adapter.verify_refund(payload)
        if parsed["status"] != "verified":
            return {"status": "rejected", "reason": parsed["reason"]}
        refund_id = parsed["refund_id"]
        if refund_id in self.processed_refund_ids:
            return {"status": "ignored_duplicate", "refund_id": refund_id}
        order = self.orders.get(parsed["order_id"])
        if not order or order.status != "paid":
            return {"status": "rejected", "reason": "unknown_or_unpaid_order"}
        if order.tenant_id != self.tenant_id or order.project_id != self.project_id:
            return {"status": "rejected", "reason": "cross_project_order"}
        if parsed.get("tenant_id") not in {None, "", order.tenant_id} or parsed.get("project_id") not in {None, "", order.project_id}:
            return {"status": "rejected", "reason": "cross_project_callback"}
        if parsed["product_code"] != order.product_code:
            return {"status": "rejected", "reason": "product_code_mismatch"}
        revoked = self.ledger.revoke_for_refund(tenant_id=order.tenant_id, project_id=order.project_id, order_id=order.order_id, product_code=order.product_code, refund_id=refund_id)
        if not revoked:
            return {"status": "rejected", "reason": "matching_entitlement_not_found"}
        order.status = "refunded"
        self.processed_refund_ids.add(refund_id)
        return {"status": "refunded", "order_id": order.order_id, "product_code": order.product_code}

    def handle_return(self, query: dict[str, Any]) -> dict[str, Any]:
        order = self.orders.get(str(query.get("order_id", "")))
        if order and (order.tenant_id != self.tenant_id or order.project_id != self.project_id):
            return {"status": "rejected", "reason": "cross_project_order"}
        return {"status": "display_only", "order_status": order.status if order else "unknown"}
