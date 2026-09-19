#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

SECRET_FIELDS = {"client_secret", "password", "otp", "cookie", "access_token", "refresh_token", "authorization_code"}
LIST_FIELDS = ("authorized_domains", "authorized_javascript_origins", "authorized_redirect_uris")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("configuration must be a JSON object")
    lowered = {str(key).lower() for key in value}
    if lowered & SECRET_FIELDS:
        raise ValueError("observed state must be sanitized and must not contain secrets or tokens")
    return value


def diff(expected: dict, observed: dict) -> dict:
    changes = []
    for field in ("application_name", "application_type"):
        if observed.get(field) != expected.get(field):
            changes.append({"field": field, "expected": expected.get(field), "observed": observed.get(field), "action": "replace"})
    for field in LIST_FIELDS:
        wanted = set(expected.get(field, []))
        current = set(observed.get(field, []))
        if wanted - current or current - wanted:
            changes.append({"field": field, "add": sorted(wanted - current), "review_before_remove": sorted(current - wanted), "action": "merge_preserving_valid_existing"})
    return {"status": "in_sync" if not changes else "changes_required", "changes": changes, "configuration_fingerprint": expected.get("configuration_fingerprint")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe Google OAuth configuration diff for this project")
    parser.add_argument("command", choices=["plan", "diff", "verify"])
    parser.add_argument("--observed", type=Path)
    args = parser.parse_args()
    expected = load(Path(__file__).with_name("google-oauth-config-manifest.json"))
    if args.command == "plan":
        print(json.dumps(expected, ensure_ascii=False, indent=2))
        return 0
    if not args.observed:
        parser.error("--observed is required for diff or verify")
    result = diff(expected, load(args.observed))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if args.command == "diff" or result["status"] == "in_sync" else 2


if __name__ == "__main__":
    raise SystemExit(main())
