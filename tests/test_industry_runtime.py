from __future__ import annotations

import json
import tempfile
from pathlib import Path

from server.industry_runtime import IndustryRuntime, MANIFEST


ROOT = Path(__file__).resolve().parents[1]


def make_runtime(tmp: str) -> IndustryRuntime:
    runtime = IndustryRuntime(Path(tmp))
    runtime.catalog_path.write_bytes((ROOT / "data" / "runtime-catalog.json").read_bytes())
    return runtime


def test_search_detail_and_widget_actions_are_behavioral():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = make_runtime(tmp)
        result = runtime.call('notification_delivery_status', {'query': '示範', 'page_size': 1})
        assert result["structuredContent"]["pagination"]["total_count"] == 1
        assert result["structuredContent"]["items"][0]["id"] == "demo-001"
        assert any(action["tool_name"] for action in result["structuredContent"]["actions"])
        detail = runtime.get("demo-001")
        assert detail["structuredContent"]["content_type"] == "detail"


def test_supplier_import_is_candidate_first_and_publish_is_explicit():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = make_runtime(tmp)
        invalid = runtime.create_candidate("supplier-demo", [{"id": "bad"}])
        assert invalid["can_publish"] is False
        assert runtime.publish_candidate(invalid["batch_id"])["status"] == "validation_failed"
        invalid_number = runtime.create_candidate("supplier-demo", [{"id": "bad-number", "name": "錯誤", "status": "published", "price": "free", "inventory": -1}])
        assert invalid_number["can_publish"] is False
        valid = runtime.create_candidate("supplier-demo", [{'id': 'new-1', 'name': '新項目', 'status': 'published', 'updated_at': '2099-01-01T00:00:00Z'}])
        assert valid["can_publish"] is True
        assert runtime.publish_candidate(valid["batch_id"])["status"] == "published"
        assert runtime.get("new-1")["structuredContent"]["items"][0]["title"] == "新項目"


def test_write_or_transaction_requires_confirmation_and_never_claims_live_payment():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = make_runtime(tmp)
        tool = 'create_booking'
        blocked = runtime.call(tool, {'item_id': 'demo-001', 'quantity': 1})
        assert blocked["status"] == "confirmation_required"
        completed = runtime.call(tool, {'item_id': 'demo-001', 'quantity': 1, 'confirmed': True, 'idempotency_key': 'test-transaction-1'})
        assert completed["status"] in {"ok", "created", "accepted", "checkpoint_saved", "sandbox_pending_payment", "sandbox_redirect_ready", "cart_created", "draft", "queued", "sandbox_email_prepared", "sandbox_workflow_prepared"}
        assert completed.get("payment_provider_enabled") is not True
        repeated = runtime.call(tool, {'item_id': 'demo-001', 'quantity': 1, 'confirmed': True, 'idempotency_key': 'test-transaction-1'})
        assert repeated == completed



def test_csv_file_is_parsed_into_a_candidate_batch():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = make_runtime(tmp)
        csv_data = ('id,name,status,updated_at' + "\n" + 'new-1,新項目,published,2099-01-01T00:00:00Z' + "\n").encode("utf-8")
        result = runtime.create_candidate_from_file("supplier-demo", "items.csv", csv_data)
        assert result["status"] == "candidate"
        assert result["can_publish"] is True


def test_manifest_and_import_contract_are_domain_owned():
    manifest = json.loads((ROOT / "generated_mcp" / "runtime-capability-manifest.json").read_text(encoding="utf-8"))
    contract = json.loads((ROOT / "imports" / "import-contract.json").read_text(encoding="utf-8"))
    assert manifest["domain_id"] == 'automotive'
    assert contract["domain_id"] == 'automotive'
    assert "explicit_publish" in contract["workflow"]
    assert MANIFEST["display_name"] in json.dumps(manifest, ensure_ascii=False)


