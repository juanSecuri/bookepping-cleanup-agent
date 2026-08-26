-- Fiscal year close: P&L nets roll into Retained Earnings (3020)
-- Applied remotely as: fiscal_year_closes

CREATE TABLE IF NOT EXISTS fiscal_year_closes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    fiscal_year         TEXT NOT NULL CHECK (fiscal_year ~ '^\d{4}$'),
    currency            TEXT NOT NULL DEFAULT 'USD',
    total_revenue       NUMERIC(18,2) NOT NULL DEFAULT 0,
    total_expenses      NUMERIC(18,2) NOT NULL DEFAULT 0,
    net_income          NUMERIC(18,2) NOT NULL DEFAULT 0,
    equity_draws_net    NUMERIC(18,2) NOT NULL DEFAULT 0,
    transaction_count   INT NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'closed'
                          CHECK (status IN ('closed', 'reopened')),
    notes               TEXT,
    closed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    reopened_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, fiscal_year)
);

CREATE INDEX IF NOT EXISTS idx_fiscal_year_closes_tenant
  ON fiscal_year_closes (tenant_id, fiscal_year DESC);

ALTER TABLE fiscal_year_closes ENABLE ROW LEVEL SECURITY;
