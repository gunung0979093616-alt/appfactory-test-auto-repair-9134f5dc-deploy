from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mcp_release_contract_is_project_scoped_and_fail_closed():
    contract = json.loads((ROOT / "project_sync_guards" / "mcp-release-inheritance-contract.json").read_text(encoding="utf-8"))
    assert contract["project_public_tools"]
    assert set(contract["project_public_tools"]) != set(contract["public_surface_policy"]["mother_router_tools_forbidden_as_child_surface"])
    assert len(contract["stage_release_gates"]) == 6
    assert contract["evidence_dependency"]["server_mcp_pass_is_not_native_chatgpt_pass"] is True
    assert contract["evidence_dependency"]["local_pass_is_not_production_pass"] is True
    assert contract["regression_invalidation"]["action"].startswith("Mark affected")
