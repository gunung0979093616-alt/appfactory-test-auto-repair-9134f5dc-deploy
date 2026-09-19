-- Stage 4 schema scaffold. Apply through the project's migration system.
CREATE TABLE payment_plan_versions (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  product_code TEXT NOT NULL,
  plan_version TEXT NOT NULL,
  lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('draft','scheduled','active','retired')),
  confirmed_at TEXT,
  scheduled_at TEXT,
  activated_at TEXT,
  retired_at TEXT,
  plan_snapshot_json TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, product_code, plan_version)
);
CREATE TABLE payment_orders (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  order_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  product_code TEXT NOT NULL,
  billing_model TEXT NOT NULL,
  plan_version TEXT NOT NULL,
  server_amount INTEGER NOT NULL CHECK (server_amount > 0),
  entitlement_kind_snapshot TEXT NOT NULL,
  credits_snapshot INTEGER NOT NULL DEFAULT 0,
  valid_days_snapshot INTEGER,
  currency TEXT NOT NULL DEFAULT 'TWD',
  status TEXT NOT NULL,
  provider_transaction_id TEXT,
  paid_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, order_id),
  UNIQUE (tenant_id, project_id, provider_transaction_id)
);
CREATE TABLE provider_transactions (tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, provider_transaction_id TEXT NOT NULL, order_id TEXT NOT NULL, verified_status TEXT NOT NULL, verified_at TEXT NOT NULL, PRIMARY KEY (tenant_id, project_id, provider_transaction_id));
CREATE TABLE notify_receipts (tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, receipt_id TEXT NOT NULL, order_id TEXT NOT NULL, payload_digest TEXT NOT NULL, verification_status TEXT NOT NULL, received_at TEXT NOT NULL, PRIMARY KEY (tenant_id, project_id, receipt_id));
CREATE TABLE entitlements (tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, entitlement_id TEXT NOT NULL, order_id TEXT NOT NULL, user_id TEXT NOT NULL, product_code TEXT NOT NULL, billing_model TEXT NOT NULL, status TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT, units_granted INTEGER NOT NULL DEFAULT 0, units_remaining INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (tenant_id, project_id, entitlement_id));
CREATE TABLE usage_ledger (tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, usage_id TEXT NOT NULL, entitlement_id TEXT NOT NULL, units INTEGER NOT NULL, idempotency_key TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (tenant_id, project_id, usage_id), UNIQUE (tenant_id, project_id, idempotency_key));
CREATE TABLE refund_records (tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, refund_id TEXT NOT NULL, order_id TEXT NOT NULL, product_code TEXT NOT NULL, provider_transaction_id TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (tenant_id, project_id, refund_id));
-- Rollback changes only which preserved plan version receives new orders. Never UPDATE historical order snapshots.
