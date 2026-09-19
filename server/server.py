from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from server.project_stage234_runtime import PROJECT_STAGE234_ROUTES
from server.stage56_runtime import stage5_evidence, stage5_readiness, stage6_enqueue, stage6_rollback, stage6_run_once, stage6_status

from server.industry_runtime import IndustryRuntime


TOOLS = [{'name': 'schedule_operation', 'description': '確認資源、時間與影響範圍後建立排程。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'subscribe_alerts', 'description': '確認通知對象與管道後建立異常通知。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'create_booking', 'description': '重新檢查名額與輸入並確認後建立預約。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'booking_id': {'type': 'string'}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'approve_task', 'description': '核准任務：依輸入、前置條件與成功條件執行，不以產業名稱代替需求判斷。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'send_notification', 'description': '發送通知：依輸入、前置條件與成功條件執行，不以產業名稱代替需求判斷。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'assign_technician', 'description': '指派技師：依輸入、前置條件與成功條件執行，不以產業名稱代替需求判斷。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'record_parts_usage', 'description': '零件使用紀錄：依輸入、前置條件與成功條件執行，不以產業名稱代替需求判斷。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'base_id': {'type': 'string'}, 'table_id': {'type': 'string'}, 'record_id': {'type': 'string'}, 'view_id': {'type': 'string'}, 'revision': {'type': 'string'}, 'cursor': {'type': 'string'}, 'field_values': {'type': 'object'}, 'records': {'type': 'array', 'items': {'type': 'object'}}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'book_notification', 'description': 'book notification：依輸入、前置條件與成功條件執行，不以產業名稱代替需求判斷。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'cancel_notification', 'description': '取消通知：依輸入、前置條件與成功條件執行，不以產業名稱代替需求判斷。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'notification_delivery_status', 'description': '通知狀態：依輸入、前置條件與成功條件執行，不以產業名稱代替需求判斷。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'store_id': {'type': 'string'}, 'buyer_id': {'type': 'string'}, 'cart_id': {'type': 'string'}, 'variant_id': {'type': 'string'}, 'order_id': {'type': 'string'}}, 'required': [], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'retry_notification', 'description': '重送通知：依輸入、前置條件與成功條件執行，不以產業名稱代替需求判斷。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'schedule_job', 'description': '排程工作：依輸入、前置條件與成功條件執行，不以產業名稱代替需求判斷。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}, {'name': 'schedule_reminder', 'description': '排程提醒：依輸入、前置條件與成功條件執行，不以產業名稱代替需求判斷。', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'page': {'type': 'integer', 'minimum': 1}, 'page_size': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 1}, 'confirmed': {'type': 'boolean'}, 'idempotency_key': {'type': 'string'}}, 'required': ['confirmed', 'idempotency_key'], 'additionalProperties': True}, 'securitySchemes': [{'type': 'noauth'}], '_meta': {'securitySchemes': [{'type': 'noauth'}], 'ui': {'resourceUri': 'ui://widget/universal-industry-content-v1.html'}, 'openai/outputTemplate': 'ui://widget/universal-industry-content-v1.html'}}]
RESOURCE_URI = "ui://widget/universal-industry-content-v1.html"
RESOURCE_MIME = "text/html;profile=mcp-app"
RUNTIME = IndustryRuntime(Path(os.getenv("APP_DATA_DIR", "data")))


def _prefers_browser_html(request: Request) -> bool:
    requested_format = request.query_params.get("format", "").strip().lower()
    if requested_format == "json":
        return False
    return requested_format == "html" or request.headers.get("sec-fetch-dest", "").lower() == "document" or "text/html" in request.headers.get("accept", "").lower()


async def health(request: Request) -> JSONResponse:
    payload = {"status": "ok", "service": 'auto-repair', "public_tools_count": len(TOOLS)}
    if _prefers_browser_html(request):
        return HTMLResponse(_health_page(payload))
    return JSONResponse(payload, headers={"Content-Type": "application/json; charset=utf-8"})


async def deployment_status(request: Request) -> JSONResponse:
    external_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    payload = {
        "status": "ok",
        "service": 'auto-repair',
        "environment": os.getenv("APP_ENV", "local"),
        "render_service_id": os.getenv("RENDER_SERVICE_ID", ""),
        "render_workspace_id": os.getenv("RENDER_WORKSPACE_ID", ""),
        "render_external_url": external_url,
        "health_url": f"{external_url}/health" if external_url else "",
        "mcp_url": f"{external_url}/mcp" if external_url else "/mcp",
        "git_commit": os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT", ""),
        "public_tools_count": len(TOOLS),
        "render_api_management": "server_side_env_only",
        "plain_language": "這裡用來確認正式站是不是最新版、MCP 是否有入口、Render 服務資料是否已設定；金鑰不會顯示在前端。",
    }
    return JSONResponse(payload, headers={"Content-Type": "application/json; charset=utf-8"})


async def deployment_smoke(request: Request) -> JSONResponse:
    external_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    checks = {
        "health_endpoint_present": True,
        "mcp_endpoint_present": True,
        "render_commit_present": bool(os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT", "")),
        "render_service_id_configured": bool(os.getenv("RENDER_SERVICE_ID", "").strip()),
        "render_workspace_id_configured": bool(os.getenv("RENDER_WORKSPACE_ID", "").strip()),
        "external_url_configured": bool(external_url),
    }
    status = "ready_for_live_probe" if checks["external_url_configured"] else "waiting_for_render_external_url"
    return JSONResponse({
        "status": status,
        "checks": checks,
        "next_live_checks": [
            "GET /health must return JSON status ok",
            "POST /mcp initialize must pass",
            "POST /mcp tools/list must include this project tools",
            "POST /mcp tools/call must call at least one read-only tool",
            "ChatGPT native connection and screenshots remain separate evidence",
        ],
        "truth_boundary": "This local API confirms the generated project has deployment-management surfaces. It does not call Render API unless the owner configures server-side Render credentials outside source control.",
    })


def _health_page(payload: dict) -> str:
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>系統健康狀態</title></head><body><main><h1>服務運作正常</h1><p>服務：{payload["service"]}</p><p>狀態：{payload["status"]}</p><p>這只代表網站可連線；MCP 與 ChatGPT 原生畫面需分別驗證。</p><p><a href="/">返回首頁</a></p></main></body></html>"""


async def mcp(request: Request) -> JSONResponse:
    if os.getenv("MCP_AUTH_MODE", "none").strip().lower() != "none":
        return JSONResponse({"error": "mcp_oauth_not_materialized", "message": "MCP OAuth 必須先完成獨立授權實作與驗證，不能把會員 Google 登入當成 MCP OAuth。"}, status_code=503)
    payload = await request.json()
    method = payload.get("method")
    request_id = payload.get("id")
    if method == "initialize":
        result = {"protocolVersion": "2026-07-28", "capabilities": {"tools": {"listChanged": False}, "resources": {"listChanged": False}}, "serverInfo": {"name": 'auto-repair', "version": "1.1.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "resources/list":
        result = {"resources": [{"uri": RESOURCE_URI, "name": "跨產業互動內容", "mimeType": RESOURCE_MIME}]}
    elif method == "resources/read":
        uri = (payload.get("params") or {}).get("uri")
        if uri != RESOURCE_URI:
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "unknown resource"}})
        widget = Path("frontend/rich_media_interactive_ui/universal-industry-content-v1.html").read_text(encoding="utf-8")
        result = {"contents": [{"uri": RESOURCE_URI, "mimeType": RESOURCE_MIME, "text": widget}]}
    elif method == "tools/call":
        params = payload.get("params") or {}
        name = params.get("name")
        if name not in {item["name"] for item in TOOLS}:
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "unknown tool"}})
        runtime_result = RUNTIME.call(name, params.get("arguments") or {})
        result = {"content": [{"type": "text", "text": json.dumps(runtime_result, ensure_ascii=False)}], "isError": False}
        if runtime_result.get("structuredContent"):
            result["structuredContent"] = runtime_result["structuredContent"]
    else:
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method not found"}})
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


async def mcp_browser(request: Request):
    if _prefers_browser_html(request):
        return HTMLResponse("""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MCP 連接網址</title></head><body><main><h1>MCP 連接網址</h1><p>這是提供給 ChatGPT 使用的連接網址。瀏覽器看到本說明頁，只代表網址可到達；仍須完成 MCP 初始化、工具清單與工具呼叫驗證。</p></main></body></html>""")
    return PlainTextResponse("MCP requests must use POST", status_code=405, headers={"Allow": "POST, OPTIONS"})


def _admin_authorized(request: Request) -> tuple[bool, int, str]:
    configured = os.getenv("ADMIN_IMPORT_CREDENTIAL", "").strip()
    if not configured or configured == "configure-outside-source-control":
        return False, 503, "管理匯入尚未設定"
    supplied = request.headers.get("x-admin-token", "")
    return (True, 200, "") if hmac.compare_digest(configured, supplied) else (False, 403, "權限不足")


async def create_import_candidate(request: Request) -> JSONResponse:
    allowed, status_code, message = _admin_authorized(request)
    if not allowed:
        return JSONResponse({"status": "error", "message": message}, status_code=status_code)
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            return JSONResponse({"status": "error", "message": "請選擇 CSV、JSON 或 XLSX 檔案"}, status_code=400)
        content = await upload.read()
        if len(content) > 5 * 1024 * 1024:
            return JSONResponse({"status": "error", "message": "檔案不可超過 5 MB"}, status_code=413)
        return JSONResponse(RUNTIME.create_candidate_from_file(str(form.get("supplier_id", "")), str(upload.filename or ""), content))
    payload = await request.json()
    return JSONResponse(RUNTIME.create_candidate(str(payload.get("supplier_id", "")), payload.get("rows") or []))


async def publish_import_candidate(request: Request) -> JSONResponse:
    allowed, status_code, message = _admin_authorized(request)
    if not allowed:
        return JSONResponse({"status": "error", "message": message}, status_code=status_code)
    return JSONResponse(RUNTIME.publish_candidate(request.path_params["batch_id"]))


async def redeem_voucher(request: Request) -> JSONResponse:
    allowed, status_code, message = _admin_authorized(request)
    if not allowed:
        return JSONResponse({"status": "error", "message": message}, status_code=status_code)
    payload = await request.json()
    return JSONResponse(RUNTIME.redeem(str(payload.get("voucher_id", "")), confirmed=bool(payload.get("confirmed"))))


async def supplier_template(request: Request) -> PlainTextResponse:
    content = Path("imports/supplier-catalog-template.csv").read_text(encoding="utf-8")
    return PlainTextResponse(content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="supplier-catalog-template.csv"'})


app = Starlette(routes=[
    Route("/api/stage5/readiness", stage5_readiness, methods=["GET"]),
    Route("/api/stage5/evidence", stage5_evidence, methods=["POST"]),
    Route("/api/stage6/status", stage6_status, methods=["GET"]),
    Route("/api/stage6/sync/enqueue", stage6_enqueue, methods=["POST"]),
    Route("/api/stage6/sync/run-once", stage6_run_once, methods=["POST"]),
    Route("/api/stage6/rollback", stage6_rollback, methods=["POST"]),
    *PROJECT_STAGE234_ROUTES,
    Route("/health", health, methods=["GET"]),
    Route("/mcp", mcp_browser, methods=["GET"]),
    Route("/mcp", mcp, methods=["POST"]),
    Route("/api/admin/deployment/status", deployment_status, methods=["GET"]),
    Route("/api/admin/deployment/smoke", deployment_smoke, methods=["POST"]),
    Route("/api/admin/imports", create_import_candidate, methods=["POST"]),
    Route("/api/admin/imports/{batch_id}/publish", publish_import_candidate, methods=["POST"]),
    Route("/api/vouchers/redeem", redeem_voucher, methods=["POST"]),
    Route("/supplier-template.csv", supplier_template, methods=["GET"]),
    Mount("/", app=StaticFiles(directory="frontend_site", html=True), name="frontend"),
])
app = CORSMiddleware(
    app,
    allow_origins=[origin.strip() for origin in os.getenv("MCP_ALLOWED_ORIGINS", "https://chatgpt.com,https://chat.openai.com").split(",") if origin.strip()],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "MCP-Protocol-Version", "Mcp-Session-Id", "Last-Event-ID"],
    expose_headers=["Mcp-Session-Id", "WWW-Authenticate"],
)
