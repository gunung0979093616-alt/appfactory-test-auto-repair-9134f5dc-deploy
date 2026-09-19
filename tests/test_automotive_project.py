from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_domain_schema_and_tools_are_generated():
    schema = json.loads((ROOT / "data_schema" / "automotive-schema.json").read_text(encoding="utf-8"))
    assert [field["name"] for field in schema["fields"]] == ['id', 'name', 'description', 'status', 'created_at', 'updated_at', 'category', 'source', 'owner_id']
    payload = json.loads((ROOT / "generated_mcp" / "automotive-tools.json").read_text(encoding="utf-8"))
    assert [tool["name"] for tool in payload["tools"]] == ['schedule_operation', 'subscribe_alerts', 'create_booking', 'approve_task', 'send_notification', 'assign_technician', 'record_parts_usage', 'book_notification', 'cancel_notification', 'notification_delivery_status', 'retry_notification', 'schedule_job', 'schedule_reminder']
    intent = json.loads((ROOT / "requirements" / "intent-contract.json").read_text(encoding="utf-8"))
    assert intent["requirements_frozen"] is True
    assert intent["required_tools_source"] != "promoted_from_runtime_manifest"
    assert intent["requirement_fingerprint"] == '234cf1065c25417738679315d66b616ad99fbd9291e8fecbdb45cc34bc151aa7'
    assert intent["required_tools"] == ['schedule_operation', 'subscribe_alerts', 'create_booking', 'approve_task', 'send_notification', 'assign_technician', 'record_parts_usage', 'book_notification']
    assert set(intent["required_tools"]).issubset(set(['schedule_operation', 'subscribe_alerts', 'create_booking', 'approve_task', 'send_notification', 'assign_technician', 'record_parts_usage', 'book_notification', 'cancel_notification', 'notification_delivery_status', 'retry_notification', 'schedule_job', 'schedule_reminder']))
    trace = json.loads((ROOT / "validation" / "requirements_traceability" / "intent-runtime-trace.json").read_text(encoding="utf-8"))
    assert trace["status"] == "PASS"
    assert trace["requirement_fingerprint"] == intent["requirement_fingerprint"]
    skill_manifest = json.loads((ROOT / "skills" / "skill-cluster-manifest.json").read_text(encoding="utf-8"))
    assert skill_manifest["status"] == "PASS"
    assert skill_manifest["checks"]["all_tools_mapped_to_skills"] == "PASS"
    assert not skill_manifest["unmapped_tools"]
    if len(['schedule_operation', 'subscribe_alerts', 'create_booking', 'approve_task', 'send_notification', 'assign_technician', 'record_parts_usage', 'book_notification', 'cancel_notification', 'notification_delivery_status', 'retry_notification', 'schedule_job', 'schedule_reminder']) >= 8:
        assert skill_manifest["skill_count"] >= 2
        assert skill_manifest["checks"]["complex_project_not_single_skill"] == "PASS"
    contract = json.loads((ROOT / "requirements" / "capability-contract.json").read_text(encoding="utf-8"))
    assert contract["status"] == "PASS"
    assert contract["capability_groups"]["required"] == ['schedule_operation', 'subscribe_alerts', 'create_booking', 'approve_task', 'send_notification', 'assign_technician', 'record_parts_usage', 'book_notification']
    assert contract["missing_required_capabilities"] == []
    assert contract["requirement_fingerprint"] == '234cf1065c25417738679315d66b616ad99fbd9291e8fecbdb45cc34bc151aa7'
    assert all((ROOT / item["skill_behavior"]).exists() for item in contract["capabilities"])


def test_deployable_surfaces_and_fail_closed_payment_exist():
    import py_compile
    server = (ROOT / "server" / "server.py").read_text(encoding="utf-8")
    assert 'Route("/health"' in server
    assert 'Route("/mcp"' in server
    assert 'Route("/api/admin/deployment/status"' in server
    assert 'Route("/api/admin/deployment/smoke"' in server
    assert 'StaticFiles(directory="frontend_site", html=True)' in server
    assert "2026-07-28" in server
    assert "sec-fetch-dest" in server
    assert "_prefers_browser_html" in server
    assert "application/json; charset=utf-8" in server
    assert (ROOT / "deployment" / "render-management-contract.json").exists()
    assert (ROOT / "frontend_site" / "admin" / "deployment.html").exists()
    assert (ROOT / "validation" / "deployment_ops" / "deployment-ops-validation.json").exists()
    contract = json.loads((ROOT / "deployment" / "render-management-contract.json").read_text(encoding="utf-8"))
    assert contract["generated_surfaces"]["status_api"] == "/api/admin/deployment/status"
    assert contract["generated_surfaces"]["smoke_api"] == "/api/admin/deployment/smoke"
    assert "RENDER_API_KEY" in json.dumps(contract, ensure_ascii=False)
    assert "PUBLIC_CHECKOUT_ENABLED=false" in (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "RENDER_API_KEY=" not in (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "runtime: python" in (ROOT / "render.yaml").read_text(encoding="utf-8")
    py_compile.compile(str(ROOT / "server" / "server.py"), doraise=True)


def test_project_is_not_contaminated_by_fixed_reference_templates():
    all_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in ROOT.rglob("*") if path.is_file() and "tests" not in path.parts and path.suffix in {".md", ".json", ".py", ".yaml"})
    assert "government-subsidy-schema" not in all_text
    assert "taiwan-fire-public-mcp" not in all_text
