from __future__ import annotations

import json
import tempfile
from pathlib import Path

from server.industry_runtime import IndustryRuntime
from server.server import TOOLS


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = {
    "diagnose_wait_bottlenecks", "list_repair_work_queue", "get_repair_order",
    "create_vehicle_intake", "create_repair_order", "assign_repair_bay",
    "match_technician_skills", "mark_parts_wait", "request_quote_approval",
    "update_repair_status", "notify_repair_customer", "complete_vehicle_handover",
}


def test_public_tools_match_owner_repair_operations_not_car_sales():
    assert {tool["name"] for tool in TOOLS} == EXPECTED_TOOLS
    assert len(TOOLS) == 12
    assert all("annotations" in tool for tool in TOOLS)
    homepage = (ROOT / "frontend_site" / "index.html").read_text(encoding="utf-8")
    assert "等待時間根因診斷" in homepage
    assert "接車到交車" in homepage
    assert "搜尋車款" not in homepage
    assert "預約試駕" not in homepage


def test_repair_workflow_has_domain_state_and_idempotency():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = IndustryRuntime(Path(tmp))
        diagnosis = runtime.call("diagnose_wait_bottlenecks", {"shop_id": "shop-01"})
        assert diagnosis["root_cause_verified"] is False
        assert diagnosis["next_step"] == "collect_real_event_timestamps_before_freezing_solution"

        blocked = runtime.call("create_vehicle_intake", {"shop_id": "shop-01", "plate_number": "TEST-001", "customer_concern": "異音"})
        assert blocked["status"] == "confirmation_required"
        intake_args = {"shop_id": "shop-01", "plate_number": "TEST-001", "mileage_km": 42000, "customer_concern": "異音", "confirmed": True, "idempotency_key": "intake-1"}
        intake = runtime.call("create_vehicle_intake", intake_args)
        assert runtime.call("create_vehicle_intake", intake_args) == intake
        order = runtime.call("create_repair_order", {"intake_id": intake["vehicle_intake"]["id"], "inspection_items": ["底盤", "煞車"], "confirmed": True, "idempotency_key": "order-1"})
        order_id = order["repair_order"]["id"]
        bay = runtime.call("assign_repair_bay", {"repair_order_id": order_id, "bay_id": "bay-01", "confirmed": True, "idempotency_key": "bay-1"})
        assert bay["repair_order"]["bay_id"] == "bay-01"
        matched = runtime.call("match_technician_skills", {"repair_order_id": order_id})
        assert matched["assignment_changed"] is False
        parts = runtime.call("mark_parts_wait", {"repair_order_id": order_id, "part_name": "來令片", "estimated_arrival": "2026-09-20", "confirmed": True, "idempotency_key": "parts-1"})
        assert parts["repair_order"]["status"] == "waiting_parts"
        quote = runtime.call("request_quote_approval", {"repair_order_id": order_id, "amount": 6800, "quote_items": ["來令片", "工資"], "confirmed": True, "idempotency_key": "quote-1"})
        assert quote["repair_order"]["quote"]["approval"] == "pending"
        notification = runtime.call("notify_repair_customer", {"repair_order_id": order_id, "channel": "line", "message": "報價待確認", "confirmed": True, "idempotency_key": "notify-1"})
        assert notification["repair_order"]["notifications"][0]["external_delivery_completed"] is False
        handover = runtime.call("complete_vehicle_handover", {"repair_order_id": order_id, "quality_check_passed": True, "confirmed": True, "idempotency_key": "handover-1"})
        assert handover["repair_order"]["status"] == "completed"


def test_tool_annotations_and_write_contract_are_consistent():
    payload = json.loads((ROOT / "generated_mcp" / "automotive-operations-tools.json").read_text(encoding="utf-8"))
    for tool in payload["tools"]:
        is_read = tool["action_kind"] == "read"
        assert tool["annotations"]["readOnlyHint"] is is_read
        required = set(tool["inputSchema"].get("required", []))
        if not is_read:
            assert {"confirmed", "idempotency_key"}.issubset(required)
