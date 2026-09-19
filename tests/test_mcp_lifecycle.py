from __future__ import annotations

from starlette.testclient import TestClient

from server.server import app


def _sample_value(schema):
    if "default" in schema:
        return schema["default"]
    kind = schema.get("type")
    if kind == "boolean":
        return False
    if kind in {"integer", "number"}:
        return 1
    if kind == "array":
        return []
    if kind == "object":
        return {}
    return "測試"


def test_mcp_server_starts_handles_protocol_requests_and_stops_cleanly(monkeypatch):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(app) as client:
        health = client.get("/health")
        browser_health = client.get("/health", headers={"Accept": "text/html"})
        mobile_browser_health = client.get("/health", headers={"Accept": "*/*", "Sec-Fetch-Dest": "document"})
        browser_mcp = client.get("/mcp", headers={"Accept": "text/html", "Sec-Fetch-Dest": "document"})
        protocol_get = client.get("/mcp", headers={"Accept": "application/json, text/event-stream"})
        preflight = client.options(
            "/mcp",
            headers={
                "Origin": "https://chatgpt.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,mcp-protocol-version,mcp-session-id,authorization",
            },
        )
        initialized = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "generated-project-lifecycle-test", "version": "1.0"},
                },
            },
        )
        listed = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        tools = listed.json()["result"]["tools"]
        first_tool = tools[0]
        input_schema = first_tool.get("inputSchema") or {"type": "object", "properties": {}}
        properties = input_schema.get("properties") or {}
        arguments = {name: _sample_value(properties.get(name) or {}) for name in input_schema.get("required") or []}
        called = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": first_tool["name"], "arguments": arguments}},
        )
        monkeypatch.setenv("MCP_AUTH_MODE", "oauth")
        auth_blocked = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 9, "method": "initialize", "params": {}},
        )

    assert health.status_code == 200
    assert health.headers["content-type"] == "application/json; charset=utf-8"
    assert browser_health.status_code == 200
    assert "服務運作正常" in browser_health.text
    assert mobile_browser_health.status_code == 200
    assert "服務運作正常" in mobile_browser_health.text
    assert browser_mcp.status_code == 200
    assert "MCP 連接網址" in browser_mcp.text
    assert protocol_get.status_code in {200, 405}
    if protocol_get.status_code == 405:
        assert "POST" in protocol_get.headers.get("allow", "")
    assert preflight.status_code in {200, 204}
    assert preflight.headers.get("access-control-allow-origin") == "https://chatgpt.com"
    assert initialized.status_code in {200, 202}
    assert "result" in initialized.json()
    assert listed.status_code == 200
    assert listed.json()["result"]["tools"]
    assert called.status_code == 200
    assert "result" in called.json()
    assert called.json()["result"].get("isError") is not True
    assert auth_blocked.status_code == 503
    assert auth_blocked.json()["error"] == "mcp_oauth_not_materialized"
