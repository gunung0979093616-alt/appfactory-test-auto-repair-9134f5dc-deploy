from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any
from urllib.parse import parse_qs, urlencode

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class PayuniAdapter:
    """PAYUNi UPP v2.0 adapter using the official AES-256-GCM envelope.

    Secrets come only from constructor arguments or deployment environment variables.
    ReturnURL never grants entitlement; only verified Notify/webhook or verified trade query can mark paid.
    """

    UPP_VERSION = "2.0"
    UPP_SANDBOX_URL = "https://sandbox-api.payuni.com.tw/api/upp"
    UPP_PRODUCTION_URL = "https://api.payuni.com.tw/api/upp"
    TRADE_QUERY_VERSION = "2.0"
    CREDIT_REFUND_CLOSE_VERSION = "1.0"
    CREDIT_TOKEN_CHARGE_VERSION = "1.3"

    def __init__(self, *, merchant_id: str | None = None, hash_key: str | None = None,
                 hash_iv: str | None = None, environment: str | None = None,
                 return_url: str | None = None, notify_url: str | None = None,
                 allow_test_fixtures: bool = False) -> None:
        self.merchant_id = (merchant_id or os.environ.get("PAYUNI_MERCHANT_ID", "")).strip()
        self.hash_key = (hash_key or os.environ.get("PAYUNI_HASH_KEY", "")).strip()
        self.hash_iv = (hash_iv or os.environ.get("PAYUNI_HASH_IV", "")).strip()
        self.environment = (environment or os.environ.get("PAYUNI_ENVIRONMENT", "sandbox")).strip().lower()
        self.return_url = (return_url or os.environ.get("PAYUNI_RETURN_URL", "")).strip()
        self.notify_url = (notify_url or os.environ.get("PAYUNI_NOTIFY_URL", "")).strip()
        self.allow_test_fixtures = allow_test_fixtures

    @property
    def configured(self) -> bool:
        return bool(self.merchant_id and len(self.hash_key.encode()) == 32 and len(self.hash_iv.encode()) == 16)

    def encrypt_fields(self, fields: dict[str, Any]) -> str:
        if not self.configured:
            raise RuntimeError("payuni_secret_manager_configuration_required")
        plaintext = urlencode(fields).encode("utf-8")
        encrypted_with_tag = AESGCM(self.hash_key.encode()).encrypt(self.hash_iv.encode(), plaintext, None)
        ciphertext, tag = encrypted_with_tag[:-16], encrypted_with_tag[-16:]
        import base64
        envelope = base64.b64encode(ciphertext).decode() + ":::" + base64.b64encode(tag).decode()
        return envelope.encode().hex()

    def decrypt_fields(self, encrypted: str) -> dict[str, str]:
        if not self.configured:
            raise RuntimeError("payuni_secret_manager_configuration_required")
        import base64
        envelope = bytes.fromhex(str(encrypted)).decode()
        cipher_b64, tag_b64 = envelope.split(":::", 1)
        combined = base64.b64decode(cipher_b64) + base64.b64decode(tag_b64)
        plaintext = AESGCM(self.hash_key.encode()).decrypt(self.hash_iv.encode(), combined, None).decode()
        return {key: values[-1] for key, values in parse_qs(plaintext, keep_blank_values=True).items()}

    def hash_info(self, encrypted: str) -> str:
        material = f"{self.hash_key}{encrypted}{self.hash_iv}".encode()
        return hashlib.sha256(material).hexdigest().upper()

    def build_upp_entry(self, order: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("payuni_secret_manager_configuration_required")
        order_id = str(order["order_id"])
        if len(order_id) > 25 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in order_id):
            raise ValueError("invalid_payuni_merchant_order_id")
        encrypted = self.encrypt_fields({
            "MerID": self.merchant_id,
            "MerTradeNo": order_id,
            "TradeAmt": int(order["amount"]),
            "Timestamp": int(time.time()),
            "ReturnURL": self.return_url,
            "NotifyURL": self.notify_url,
            "ProdDesc": str(order.get("product_code") or "digital_service")[:550],
            "Credit": 1,
        })
        return {
            "method": "POST",
            "mode": "upp",
            "environment": self.environment,
            "action": self.UPP_PRODUCTION_URL if self.environment == "production" else self.UPP_SANDBOX_URL,
            "fields": {
                "MerID": self.merchant_id,
                "Version": self.UPP_VERSION,
                "EncryptInfo": encrypted,
                "HashInfo": self.hash_info(encrypted),
            },
            "server_order_reference": {
                "MerTradeNo": order["order_id"],
                "TradeAmt": order["amount"],
            },
        }

    def verify_notify(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "fixture_signature" in payload:
            if not self.allow_test_fixtures or payload.get("fixture_signature") != "valid":
                return {"status": "rejected", "reason": "bad_signature"}
            if payload.get("payment_status") != "paid":
                return {"status": "rejected", "reason": "not_paid"}
            return self._fixture_verified(payload)
        if not self.configured:
            return {"status": "rejected", "reason": "payuni_secret_manager_configuration_required"}
        encrypted = str(payload.get("EncryptInfo") or "")
        supplied_hash = str(payload.get("HashInfo") or "").upper()
        if not encrypted or not hmac.compare_digest(self.hash_info(encrypted), supplied_hash):
            return {"status": "rejected", "reason": "bad_signature"}
        try:
            result = self.decrypt_fields(encrypted)
        except (ValueError, UnicodeError):
            return {"status": "rejected", "reason": "decrypt_failed"}
        if str(payload.get("MerID") or result.get("MerID") or "") != self.merchant_id:
            return {"status": "rejected", "reason": "merchant_mismatch"}
        if str(result.get("Status") or payload.get("Status") or "").upper() != "SUCCESS" or str(result.get("TradeStatus")) != "1":
            return {"status": "rejected", "reason": "not_paid"}
        return {
            "status": "verified",
            "transaction_id": str(result["TradeNo"]),
            "order_id": str(result["MerTradeNo"]),
            "amount": int(result["TradeAmt"]),
            "product_code": "",
            "tenant_id": "",
            "project_id": "",
        }

    @staticmethod
    def _fixture_verified(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "verified", "transaction_id": str(payload["transaction_id"]),
            "order_id": str(payload["order_id"]), "amount": int(payload["amount"]),
            "product_code": str(payload.get("product_code", "")),
            "tenant_id": str(payload.get("tenant_id", "")),
            "project_id": str(payload.get("project_id", "")),
        }

    def verify_trade_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("owner_authorized") is not True:
            return {"status": "rejected", "reason": "owner_authorization_required"}
        return self.verify_notify(payload)

    def verify_refund(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.allow_test_fixtures or payload.get("fixture_signature") != "valid":
            return {"status": "rejected", "reason": "bad_signature"}
        if payload.get("refund_status") != "refunded":
            return {"status": "rejected", "reason": "not_refunded"}
        return {
            "status": "verified",
            "refund_id": str(payload["refund_id"]),
            "order_id": str(payload["order_id"]),
            "product_code": str(payload["product_code"]),
            "tenant_id": str(payload.get("tenant_id", "")),
            "project_id": str(payload.get("project_id", "")),
        }
