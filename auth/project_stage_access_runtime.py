from __future__ import annotations

TOOL_REQUIRED_STAGE = {
  "auth_oauth_login_builder": 3,
  "payment_entitlement_system_builder": 4
}
TEST_ROLES = {"owner_admin", "internal_tester", "codex_operator"}
REVIEWER_SEEDED_DEMO_TOOL_IDS = {"list_builder_capabilities", "routing_diagnostic", "analyze_deployment_feedback"}


def required_stage_for_tool(tool_id: str) -> int:
    if tool_id not in TOOL_REQUIRED_STAGE:
        raise KeyError("UNMAPPED_PROJECT_TOOL")
    return int(TOOL_REQUIRED_STAGE[tool_id])


def evaluate_stage_tool_access(*, role: str, highest_stage: int, tool_id: str, seeded_demo: bool = False) -> dict:
    try:
        required_stage = required_stage_for_tool(tool_id)
    except KeyError:
        return {"allowed": False, "status": "UNMAPPED_PROJECT_TOOL", "required_stage": None, "highest_stage": highest_stage}
    if role == "reviewer":
        if tool_id not in REVIEWER_SEEDED_DEMO_TOOL_IDS:
            return {"allowed": False, "status": "REVIEWER_READ_ONLY", "required_stage": required_stage, "highest_stage": highest_stage}
        if not seeded_demo:
            return {"allowed": False, "status": "REVIEWER_SEEDED_DEMO_REQUIRED", "required_stage": required_stage, "highest_stage": highest_stage}
        return {"allowed": True, "status": "REVIEWER_DEMO_ACCESS", "required_stage": required_stage, "highest_stage": highest_stage, "data_scope": "seeded_demo_only", "read_only": True, "not_customer_entitlement": True, "paid_entitlement": False}
    if role in TEST_ROLES:
        return {"allowed": True, "status": "TEST_ACCESS", "required_stage": required_stage, "highest_stage": highest_stage, "not_customer_entitlement": True, "paid_entitlement": False, "entitlement_source": "admin_test_bypass"}
    if highest_stage >= required_stage:
        return {"allowed": True, "status": "ENTITLED", "required_stage": required_stage, "highest_stage": highest_stage, "not_customer_entitlement": False}
    return {"allowed": False, "status": "LOCKED_STAGE", "required_stage": required_stage, "highest_stage": highest_stage, "message": f"此能力屬於第 {required_stage} 階段；目前帳號尚未解鎖。"}
