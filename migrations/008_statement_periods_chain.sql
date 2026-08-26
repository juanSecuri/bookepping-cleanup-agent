-- Statement period balances + balance-chain (cadenazo) alerts
-- Applied remotely as: statement_periods_chain

CREATE TABLE IF NOT EXISTS statement_periods (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    bank_name           TEXT NOT NULL DEFAULT '',
    bank_account_number TEXT NOT NULL DEFAULT '',
    statement_month     TEXT NOT NULL
                          CHECK (statement_month ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    opening_balance     NUMERIC(18,2),
    closing_balance     NUMERIC(18,2),
    prior_closing       NUMERIC(18,2),
    chain_delta         NUMERIC(18,2),
    chain_ok            BOOLEAN,
    paused              BOOLEAN NOT NULL DEFAULT false,
    alert_message       TEXT,
    movement_count      INT NOT NULL DEFAULT 0,
    source_document_id  UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, bank_account_number, statement_month)
);

CREATE INDEX IF NOT EXISTS idx_statement_periods_tenant
  ON statement_periods (tenant_id, statement_month DESC);

CREATE INDEX IF NOT EXISTS idx_statement_periods_alerts
  ON statement_periods (tenant_id)
  WHERE chain_ok = false OR paused = true;

ALTER TABLE statement_periods ENABLE ROW LEVEL SECURITY;

-- Owner's Draws account (equity — not P&L)
-- Upserted per-tenant by seed/app; keep global name convention in seed_coa.
