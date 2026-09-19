from __future__ import annotations

import json
import os
from pathlib import Path

from starlette.responses import JSONResponse
from starlette.routing import Route

TENANT_ID = 'tenant-7ba985c9fe58e09b'
PROJECT_ID = 'auto-repair-plugin-9134f5dc'
ENABLED_THROUGH_STAGE = 4
SESSION_COOKIE = "project_session"
_AUTH = None
_ADMIN = None
_PAYMENT = None


def _scope_error(request):
    requested_tenant = request.headers.get("x-tenant-id", TENANT_ID)
    requested_project = request.headers.get("x-project-id", PROJECT_ID)
    if requested_tenant != TENANT_ID or requested_project != PROJECT_ID:
        return JSONResponse({"status": "scope_mismatch"}, status_code=403)
    return None


def _auth_runtime():
    global _AUTH
    if ENABLED_THROUGH_STAGE < 3:
        return None
    if _AUTH is None:
        secret = os.getenv("PROJECT_SESSION_SECRET", "").strip()
        client_id = os.getenv("PROJECT_GOOGLE_CLIENT_ID", "").strip()
        test_mode = os.getenv("PROJECT_AUTH_TEST_MODE", "false").lower() == "true" and os.getenv("APP_ENV", "local") in {"local", "test"}
        if not secret or (not client_id and not test_mode):
            return None
        from auth.project_stage3_membership_runtime import Stage3Config, Stage3MembershipRuntime
        config = Stage3Config(
            google_client_id=client_id,
            session_secret=secret,
            admin_emails=frozenset(x.strip().lower() for x in os.getenv("PROJECT_ADMIN_EMAILS", "").split(",") if x.strip()),
            database_path=Path(os.getenv("PROJECT_AUTH_DB_PATH", "runtime_data/project_membership.sqlite3")),
            test_mode=test_mode,
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
        )
        _AUTH = Stage3MembershipRuntime(config)
    return _AUTH


def _principal(request):
    runtime = _auth_runtime()
    return runtime.current_user(request.cookies.get(SESSION_COOKIE, "")) if runtime else None


def _owner(request):
    principal = _principal(request)
    return principal if principal and principal.get("role") == "owner_admin" else None


def _admin_repository():
    global _ADMIN
    if _ADMIN is None:
        from website_admin_backend.admin_runtime import AdminRepository
        database_path = Path(os.getenv("PROJECT_ADMIN_DB_PATH", "runtime_data/project_admin.sqlite3"))
        database_path.parent.mkdir(parents=True, exist_ok=True)
        _ADMIN = AdminRepository(database_path)
    return _ADMIN


def _payment_api():
    global _PAYMENT
    if ENABLED_THROUGH_STAGE < 4:
        return None
    if _PAYMENT is None:
        from backend.payments.payment_api import PaymentApi
        _PAYMENT = PaymentApi(tenant_id=TENANT_ID, project_id=PROJECT_ID)
    return _PAYMENT


async def stage2_admin_status(request):
    if error := _scope_error(request):
        return error
    return JSONResponse({"status": "ready", "tenant_id": TENANT_ID, "project_id": PROJECT_ID, "identity_ready": _auth_runtime() is not None})


async def stage2_save_page(request):
    if error := _scope_error(request):
        return error
    principal = _owner(request)
    if not principal:
        return JSONResponse({"status": "owner_authentication_required"}, status_code=403 if _auth_runtime() else 503)
    payload = await request.json()
    if payload.get("confirmed") is not True:
        return JSONResponse({"status": "explicit_confirmation_required"}, status_code=409)
    page = _admin_repository().save_page(
        actor_subject=str(principal["google_sub"]), allowed_subjects={str(principal["google_sub"])},
        page_id=request.path_params["page_id"], title=str(payload.get("title") or ""),
        body=str(payload.get("body") or ""), published=bool(payload.get("published")),
    )
    return JSONResponse({"status": "saved", "tenant_id": TENANT_ID, "project_id": PROJECT_ID, "page": page})


async def stage3_status(request):
    if error := _scope_error(request):
        return error
    return JSONResponse({"status": "ready" if _auth_runtime() else "provider_configuration_required", "tenant_id": TENANT_ID, "project_id": PROJECT_ID})


async def google_login(request):
    if error := _scope_error(request):
        return error
    runtime = _auth_runtime()
    if not runtime:
        return JSONResponse({"status": "provider_configuration_required"}, status_code=503)
    payload = await request.json()
    try:
        result = runtime.login_with_google_credential(str(payload.get("credential") or ""))
    except (ValueError, PermissionError, RuntimeError) as exc:
        return JSONResponse({"status": "authentication_failed", "reason": str(exc)}, status_code=401)
    response = JSONResponse({"status": "authenticated", "user": result["user"]})
    response.set_cookie(SESSION_COOKIE, result["session"], httponly=True, secure=os.getenv("APP_ENV") == "production", samesite="lax")
    return response


async def logout(request):
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(SESSION_COOKIE)
    return response


async def account(request):
    if error := _scope_error(request):
        return error
    principal = _principal(request)
    if not principal:
        return JSONResponse({"status": "authentication_required"}, status_code=401)
    return JSONResponse({"status": "ok", "tenant_id": TENANT_ID, "project_id": PROJECT_ID, "user": principal})


async def admin_summary(request):
    if error := _scope_error(request):
        return error
    principal = _owner(request)
    if not principal:
        return JSONResponse({"status": "owner_admin_required"}, status_code=403)
    return JSONResponse({"status": "ok", "tenant_id": TENANT_ID, "project_id": PROJECT_ID, "current_user": principal})


async def billing_checkout(request):
    if error := _scope_error(request):
        return error
    principal = _principal(request)
    if not principal:
        return JSONResponse({"status": "authentication_required"}, status_code=401)
    api = _payment_api()
    if not api:
        return JSONResponse({"status": "stage4_not_materialized"}, status_code=404)
    if os.getenv("APP_ENV") == "production" and (
        os.getenv("PROJECT_PAYMENT_STORAGE_DURABLE", "false").lower() != "true"
        or not getattr(api, "durable_storage", False)
    ):
        return JSONResponse({"status": "durable_payment_storage_required"}, status_code=503)
    payload = await request.json()
    sandbox = os.getenv("PROJECT_PAYMENT_TEST_MODE", "false").lower() == "true" and os.getenv("APP_ENV", "local") in {"local", "test"}
    result = api.create_order(str(principal["id"]), str(payload.get("product_code") or ""), surface=str(payload.get("surface") or "desktop"), sandbox=sandbox)
    return JSONResponse(result, status_code=200 if result.get("status") == "pending_payment" else 409)


async def billing_notify(request):
    if error := _scope_error(request):
        return error
    api = _payment_api()
    if not api:
        return JSONResponse({"status": "stage4_not_materialized"}, status_code=404)
    if os.getenv("APP_ENV") == "production" and (
        os.getenv("PROJECT_PAYMENT_STORAGE_DURABLE", "false").lower() != "true"
        or not getattr(api, "durable_storage", False)
    ):
        return JSONResponse({"status": "durable_payment_storage_required"}, status_code=503)
    try:
        payload = await request.json()
    except Exception:
        payload = dict(await request.form())
    result = api.handle_notify(payload)
    return JSONResponse(result, status_code=200 if result.get("status") in {"paid", "ignored_duplicate"} else 401)


async def billing_return(request):
    if error := _scope_error(request):
        return error
    api = _payment_api()
    if not api:
        return JSONResponse({"status": "stage4_not_materialized"}, status_code=404)
    return JSONResponse(api.handle_return(dict(request.query_params)))


async def billing_entitlement(request):
    if error := _scope_error(request):
        return error
    principal = _principal(request)
    if not principal:
        return JSONResponse({"status": "authentication_required"}, status_code=401)
    api = _payment_api()
    if not api:
        return JSONResponse({"status": "stage4_not_materialized"}, status_code=404)
    from backend.payments.account_dashboard import account_snapshot
    return JSONResponse(account_snapshot(str(principal["id"]), api.orders, api.ledger.grants, tenant_id=TENANT_ID, project_id=PROJECT_ID))


async def billing_reconciliation(request):
    if error := _scope_error(request):
        return error
    if not _owner(request):
        return JSONResponse({"status": "owner_admin_required"}, status_code=403)
    api = _payment_api()
    if not api:
        return JSONResponse({"status": "stage4_not_materialized"}, status_code=404)
    from backend.payments.reconciliation import summarize_reconciliation
    return JSONResponse(summarize_reconciliation(api.orders, api.ledger.grants, tenant_id=TENANT_ID, project_id=PROJECT_ID))


async def billing_trade_query(request):
    if error := _scope_error(request):
        return error
    if not _owner(request):
        return JSONResponse({"status": "owner_admin_required"}, status_code=403)
    api = _payment_api()
    if not api:
        return JSONResponse({"status": "stage4_not_materialized"}, status_code=404)
    if os.getenv("APP_ENV") == "production" and (
        os.getenv("PROJECT_PAYMENT_STORAGE_DURABLE", "false").lower() != "true"
        or not getattr(api, "durable_storage", False)
    ):
        return JSONResponse({"status": "durable_payment_storage_required"}, status_code=503)
    payload = await request.json()
    payload["owner_authorized"] = True
    result = api.handle_trade_query(payload)
    return JSONResponse(result, status_code=200 if result.get("status") in {"paid", "ignored_duplicate"} else 409)


PROJECT_STAGE234_ROUTES = [
    Route("/api/stage2/admin/status", stage2_admin_status, methods=["GET"]),
    Route("/api/admin/site/pages/{page_id}", stage2_save_page, methods=["PUT"]),
]
if ENABLED_THROUGH_STAGE >= 3:
    PROJECT_STAGE234_ROUTES += [
        Route("/api/stage3/status", stage3_status, methods=["GET"]),
        Route("/api/auth/google", google_login, methods=["POST"]),
        Route("/api/auth/logout", logout, methods=["POST"]),
        Route("/api/account", account, methods=["GET"]),
        Route("/api/admin/summary", admin_summary, methods=["GET"]),
    ]
if ENABLED_THROUGH_STAGE >= 4:
    PROJECT_STAGE234_ROUTES += [
        Route("/api/billing/checkout", billing_checkout, methods=["POST"]),
        Route("/api/billing/notify", billing_notify, methods=["POST"]),
        Route("/api/billing/return", billing_return, methods=["GET"]),
        Route("/api/billing/entitlement", billing_entitlement, methods=["GET"]),
        Route("/api/admin/billing/reconciliation", billing_reconciliation, methods=["GET"]),
        Route("/payments/orders", billing_checkout, methods=["POST"]),
        Route("/payments/payuni/notify", billing_notify, methods=["POST"]),
        Route("/payments/payuni/return", billing_return, methods=["GET"]),
        Route("/account/payments", billing_entitlement, methods=["GET"]),
        Route("/admin/payments/reconciliation", billing_reconciliation, methods=["GET"]),
        Route("/admin/payments/overview", billing_reconciliation, methods=["GET"]),
        Route("/admin/payments/trade-query", billing_trade_query, methods=["POST"]),
    ]
