from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

try:
    from .project_stage3_membership_runtime import Stage3MembershipRuntime, load_stage3_config
except ImportError:
    try:
        from auth.project_stage3_membership_runtime import Stage3MembershipRuntime, load_stage3_config
    except ImportError:
        from project_stage3_membership_runtime import Stage3MembershipRuntime, load_stage3_config


def test_owner_admin_is_project_scoped_and_not_plan_gated():
    with tempfile.TemporaryDirectory() as directory:
        env = {
            "PROJECT_AUTH_DB_PATH": str(Path(directory) / "auth.sqlite3"),
            "PROJECT_AUTH_TEST_MODE": "true",
            "PROJECT_SESSION_SECRET": "local-test-secret",
            "PROJECT_GOOGLE_CLIENT_ID": "local-test-client",
            "PROJECT_ADMIN_EMAILS": "owner@example.test",
            "PROJECT_TENANT_ID": "tenant-current-customer-project",
            "PROJECT_ID": "current-customer-project",
        }
        with patch.dict(os.environ, env, clear=True):
            runtime = Stage3MembershipRuntime(load_stage3_config())
            owner = runtime.login_with_google_credential(
                "test:" + json.dumps({"sub": "owner-google-sub", "email": "owner@example.test"})
            )
            assert owner["user"]["is_admin"] is True
            assert runtime.admin_summary(owner["session"])[0] == 200
            access = runtime.authorize_stage_tool(owner["user"]["id"], "auth_oauth_login_builder")
            assert access["allowed"] is True
            assert access["paid_entitlement"] is False
            assert access["entitlement_source"] == "admin_test_bypass"
