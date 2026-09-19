from datetime import datetime, timedelta, timezone

from backend.payments.account_dashboard import account_snapshot
from backend.payments.admin_dashboard import admin_payment_snapshot
from backend.payments import payment_api as payment_module
from backend.payments.payment_api import PaymentApi as RuntimePaymentApi
from backend.payments.payuni_adapter import PayuniAdapter


TEST_PLANS = {
    "starter": {"amount": 101, "days": 30, "credits": 50, "billing_model": "fixed_term_access", "entitlement_kind": "membership", "ready": True, "plan_version": "fixture-v1", "lifecycle_status": "active"},
    "pro": {"amount": 202, "days": 60, "credits": 150, "billing_model": "fixed_term_access", "entitlement_kind": "membership", "ready": True, "plan_version": "fixture-v1", "lifecycle_status": "active"},
}


def PaymentApi(*args, **kwargs):
    kwargs.setdefault("adapter", PayuniAdapter(
        merchant_id="AAA",
        hash_key="12345678901234567890123456789012",
        hash_iv="1234567890123456",
        return_url="https://example.test/payments/return",
        notify_url="https://example.test/payments/notify",
        allow_test_fixtures=True,
    ))
    return RuntimePaymentApi(*args, **kwargs)


def test_official_payuni_aes_gcm_fixture():
    adapter = PayuniAdapter(
        merchant_id="AAA",
        hash_key="12345678901234567890123456789012",
        hash_iv="1234567890123456",
    )
    encrypted = adapter.encrypt_fields({"MerID": "AAA", "MerTradeNO": "BBB", "Prod": "商品說明"})
    assert encrypted == (
        "47396636346f66735853533167396942344f587a3775696b34732b596e70452b675270564f73536b7753446c6a4d77526d"
        "4e374256514173672b6c78616d4533504d475152642b362f4530626f446e4f6356533969756c743a3a3a4b5961342f4635"
        "456965743069385a784b6277704a413d3d"
    )
    assert adapter.decrypt_fields(encrypted) == {"MerID": "AAA", "MerTradeNO": "BBB", "Prod": "商品說明"}


def test_desktop_and_mobile_checkout_create_pending_orders_in_sandbox():
    api = PaymentApi(plans=TEST_PLANS)
    desktop = api.create_order("user_1", "starter", surface="desktop", sandbox=True)
    mobile = api.create_order("user_1", "pro", surface="mobile", sandbox=True)
    assert desktop["status"] == "pending_payment"
    assert mobile["status"] == "pending_payment"
    assert desktop["payment_entry"]["mode"] == "upp"


def test_public_checkout_is_closed_without_owner_launch_approval():
    api = PaymentApi(plans=TEST_PLANS)
    result = api.create_order("user_1", "starter", sandbox=False)
    assert result["status"] == "blocked"
    assert result["reason"] == "PUBLIC_CHECKOUT_ENABLED=false"


def test_notify_grants_entitlement_once_and_return_does_not_grant():
    api = PaymentApi(plans=TEST_PLANS)
    order = api.create_order("user_1", "starter", sandbox=True)
    order_id = order["order_id"]
    display = api.handle_return({"order_id": order_id})
    assert display["status"] == "display_only"
    assert display["order_status"] == "pending_payment"
    paid = api.handle_notify({
        "fixture_signature": "valid",
        "payment_status": "paid",
        "transaction_id": "txn_1",
        "order_id": order_id,
        "amount": 101,
    })
    duplicate = api.handle_notify({
        "fixture_signature": "valid",
        "payment_status": "paid",
        "transaction_id": "txn_1",
        "order_id": order_id,
        "amount": 101,
    })
    assert paid["status"] == "paid"
    assert paid["entitlement"]["source"] == "verified_notify"
    assert duplicate["status"] == "ignored_duplicate"


def test_bad_notify_fails_closed():
    api = PaymentApi(plans=TEST_PLANS)
    order = api.create_order("user_1", "starter", sandbox=True)
    result = api.handle_notify({
        "fixture_signature": "bad",
        "payment_status": "paid",
        "transaction_id": "txn_2",
        "order_id": order["order_id"],
        "amount": 101,
    })
    assert result["status"] == "rejected"


def test_same_amount_products_fulfill_by_product_code_not_amount():
    plans = {
        "membership": {"amount": 101, "days": 30, "credits": 10, "entitlement_kind": "membership", "ready": True, "plan_version": "fixture-v1", "lifecycle_status": "active"},
        "credit_pack": {"amount": 101, "days": 365, "credits": 100, "entitlement_kind": "credits", "ready": True, "plan_version": "fixture-v1", "lifecycle_status": "active"},
    }
    api = PaymentApi(plans=plans)
    order = api.create_order("user_1", "credit_pack", sandbox=True)
    paid = api.handle_notify({"fixture_signature": "valid", "payment_status": "paid", "transaction_id": "txn_same_amount", "order_id": order["order_id"], "amount": 101})
    assert paid["entitlement"]["product_code"] == "credit_pack"
    assert paid["entitlement"]["entitlement_kind"] == "credits"


def test_refund_revokes_only_matching_product_entitlement():
    api = PaymentApi(plans=TEST_PLANS)
    first = api.create_order("user_1", "starter", sandbox=True)
    second = api.create_order("user_1", "pro", sandbox=True)
    for transaction_id, order, amount in [("txn_a", first, 101), ("txn_b", second, 202)]:
        assert api.handle_notify({"fixture_signature": "valid", "payment_status": "paid", "transaction_id": transaction_id, "order_id": order["order_id"], "amount": amount})["status"] == "paid"
    refunded = api.handle_refund({"fixture_signature": "valid", "refund_status": "refunded", "refund_id": "refund_a", "order_id": first["order_id"], "product_code": "starter"})
    assert refunded["status"] == "refunded"
    grants = list(api.ledger.grants.values())
    assert next(item for item in grants if item["product_code"] == "starter")["status"] == "revoked_refund"
    assert next(item for item in grants if item["product_code"] == "pro")["status"] == "active"


def test_refund_rejects_wrong_product_code_and_account_isolates_users():
    api = PaymentApi(plans=TEST_PLANS)
    first = api.create_order("user_1", "starter", sandbox=True)
    second = api.create_order("user_2", "pro", sandbox=True)
    for transaction_id, order, amount in [("txn_owner", first, 101), ("txn_other", second, 202)]:
        assert api.handle_notify({"fixture_signature": "valid", "payment_status": "paid", "transaction_id": transaction_id, "order_id": order["order_id"], "amount": amount})["status"] == "paid"
    rejected = api.handle_refund({"fixture_signature": "valid", "refund_status": "refunded", "refund_id": "refund_wrong", "order_id": first["order_id"], "product_code": "pro"})
    assert rejected["reason"] == "product_code_mismatch"
    snapshot = account_snapshot("user_1", api.orders, api.ledger.grants, tenant_id=api.tenant_id, project_id=api.project_id)
    assert {order["user_id"] for order in snapshot["orders"]} == {"user_1"}
    assert {grant["user_id"] for grant in snapshot["entitlements"]} == {"user_1"}


def test_scheduled_and_retired_plans_reject_new_orders():
    for lifecycle in ["scheduled", "retired"]:
        plan = dict(TEST_PLANS["starter"], lifecycle_status=lifecycle)
        result = PaymentApi(plans={"starter": plan}).create_order("user_1", "starter", sandbox=True)
        assert result == {"status": "blocked", "reason": "plan_not_confirmed"}


def test_old_order_fulfills_from_snapshot_after_plan_update_and_rollback():
    api = PaymentApi(plans={"starter": TEST_PLANS["starter"]})
    old_order = api.create_order("user_1", "starter", sandbox=True)
    changed = dict(TEST_PLANS["starter"], amount=303, credits=999, plan_version="fixture-v2")
    assert api.register_plan_version("starter", changed)["status"] == "registered"
    paid = api.handle_notify({"fixture_signature": "valid", "payment_status": "paid", "transaction_id": "txn_snapshot", "order_id": old_order["order_id"], "amount": 101})
    assert paid["status"] == "paid"
    assert paid["entitlement"]["credits"] == 50
    assert api.rollback_plan_version("starter", "fixture-v1") == {"status": "rolled_back", "product_code": "starter", "plan_version": "fixture-v1", "history_preserved": True}
    assert api.orders[old_order["order_id"]].plan_version == "fixture-v1"


def test_product_code_cannot_be_overwritten():
    api = PaymentApi(plans={"starter": TEST_PLANS["starter"]})
    changed = dict(TEST_PLANS["starter"], product_code="different", plan_version="fixture-v2")
    assert api.register_plan_version("starter", changed) == {"status": "blocked", "reason": "product_code_is_immutable"}


def test_trade_query_requires_owner_and_is_idempotent_with_notify():
    api = PaymentApi(plans=TEST_PLANS)
    order = api.create_order("user_1", "starter", sandbox=True)
    payload = {"fixture_signature": "valid", "payment_status": "paid", "transaction_id": "txn_query", "order_id": order["order_id"], "amount": 101}
    assert api.handle_trade_query(payload)["reason"] == "owner_authorization_required"
    payload["owner_authorized"] = True
    assert api.handle_trade_query(payload)["status"] == "paid"
    assert api.handle_notify(payload)["status"] == "ignored_duplicate"


def test_admin_dashboard_tracks_purchase_activation_and_expiry():
    api = PaymentApi(plans=TEST_PLANS)
    order = api.create_order("user_1", "starter", sandbox=True)
    paid = api.handle_notify({"fixture_signature": "valid", "payment_status": "paid", "transaction_id": "txn_dates", "order_id": order["order_id"], "amount": 101})
    assert paid["status"] == "paid"
    overview = admin_payment_snapshot(api.orders, api.ledger.grants, tenant_id=api.tenant_id, project_id=api.project_id)
    row = overview["rows"][0]
    assert row["purchase_type"] == "固定期間使用"
    assert row["purchased_at"]
    assert row["access_starts_at"] == row["purchased_at"]
    assert row["access_expires_at"]
    assert row["remaining_days"] == 30
    assert row["units_remaining"] == 50


def test_fixed_term_expires_but_one_time_without_expiry_stays_active():
    now = datetime.now(timezone.utc)
    api = PaymentApi(plans=TEST_PLANS)
    order = api.create_order("user_1", "starter", sandbox=True)
    api.handle_notify({"fixture_signature": "valid", "payment_status": "paid", "transaction_id": "txn_expiry", "order_id": order["order_id"], "amount": 101})
    after_expiry = account_snapshot("user_1", api.orders, api.ledger.grants, tenant_id=api.tenant_id, project_id=api.project_id, now=now + timedelta(days=31))
    assert after_expiry["entitlements"][0]["effective_status"] == "expired"

    lifetime = {"lifetime": {"amount": 303, "days": None, "credits": 0, "billing_model": "one_time_purchase", "entitlement_kind": "lifetime_access", "ready": True, "plan_version": "fixture-v1", "lifecycle_status": "active"}}
    lifetime_api = PaymentApi(plans=lifetime)
    lifetime_order = lifetime_api.create_order("user_2", "lifetime", sandbox=True)
    lifetime_api.handle_notify({"fixture_signature": "valid", "payment_status": "paid", "transaction_id": "txn_lifetime", "order_id": lifetime_order["order_id"], "amount": 303})
    much_later = account_snapshot("user_2", lifetime_api.orders, lifetime_api.ledger.grants, tenant_id=lifetime_api.tenant_id, project_id=lifetime_api.project_id, now=now + timedelta(days=3650))
    assert much_later["entitlements"][0]["effective_status"] == "active"
    assert much_later["entitlements"][0]["valid_until"] is None


def test_kill_switches_block_new_orders_and_queue_verified_fulfillment():
    previous_acceptance = payment_module.PAYMENT_ACCEPTANCE_KILL_SWITCH
    previous_fulfillment = payment_module.ENTITLEMENT_FULFILLMENT_KILL_SWITCH
    try:
        payment_module.PAYMENT_ACCEPTANCE_KILL_SWITCH = True
        assert PaymentApi(plans=TEST_PLANS).create_order("user_1", "starter", sandbox=True)["reason"] == "payment_acceptance_kill_switch"
        payment_module.PAYMENT_ACCEPTANCE_KILL_SWITCH = False
        api = PaymentApi(plans=TEST_PLANS)
        order = api.create_order("user_1", "starter", sandbox=True)
        payload = {"fixture_signature": "valid", "payment_status": "paid", "transaction_id": "txn_queue", "order_id": order["order_id"], "amount": 101}
        payment_module.ENTITLEMENT_FULFILLMENT_KILL_SWITCH = True
        assert api.handle_notify(payload)["status"] == "queued_reconciliation"
        payment_module.ENTITLEMENT_FULFILLMENT_KILL_SWITCH = False
        assert api.handle_notify(payload)["status"] == "paid"
        assert len(api.ledger.grants) == 1
    finally:
        payment_module.PAYMENT_ACCEPTANCE_KILL_SWITCH = previous_acceptance
        payment_module.ENTITLEMENT_FULFILLMENT_KILL_SWITCH = previous_fulfillment


def test_cross_project_callback_and_dashboard_fail_closed():
    first = PaymentApi(plans=TEST_PLANS, tenant_id="tenant-a", project_id="project-a")
    second = PaymentApi(plans=TEST_PLANS, tenant_id="tenant-b", project_id="project-b")
    order = first.create_order("same-user", "starter", sandbox=True)
    callback = {
        "fixture_signature": "valid", "payment_status": "paid", "transaction_id": "txn-isolation",
        "order_id": order["order_id"], "amount": 101, "tenant_id": "tenant-b", "project_id": "project-b",
    }
    assert first.handle_notify(callback) == {"status": "rejected", "reason": "cross_project_callback"}
    assert second.handle_notify(callback) == {"status": "rejected", "reason": "unknown_order"}
    snapshot = account_snapshot("same-user", first.orders, first.ledger.grants, tenant_id="tenant-b", project_id="project-b")
    assert snapshot["orders"] == []
    assert snapshot["entitlements"] == []
