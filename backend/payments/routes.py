from __future__ import annotations


ROUTE_CONTRACTS = {
    "POST /payments/orders": "authenticated order creation using server-owned plan version",
    "POST /payments/payuni/notify": "verified provider callback and idempotent fulfillment",
    "GET /payments/payuni/return": "display-only status lookup; never grants entitlement",
    "GET /account/payments": "authenticated user's orders and entitlements",
    "GET /admin/payments/reconciliation": "owner_admin read-only reconciliation",
    "GET /admin/payments/overview": "owner_admin read-only purchase, activation, expiry, quota, refund overview",
    "POST /admin/payments/trade-query": "owner-authorized reconciliation fallback",
}


def route_contracts() -> dict[str, str]:
    return dict(ROUTE_CONTRACTS)
