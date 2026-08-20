-- ============================================================
-- Bookkeeping Clean-up Agent — Schema v0.2
-- Run in Supabase SQL Editor (or via psql)
-- FASE 2 (QuickBooks): columnas quickbooks_id están comentadas.
--   Descomentar cuando se active la integración QBO.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ── financial_transactions ───────────────────────────────────
CREATE TABLE IF NOT EXISTS financial_transactions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    transaction_date        DATE NOT NULL,
    description             TEXT NOT NULL,
    amount                  NUMERIC(18,4) NOT NULL CHECK (amount > 0),
    currency                CHAR(3) NOT NULL DEFAULT 'USD',
    transaction_type        TEXT NOT NULL,
    chart_of_accounts_code  TEXT,
    chart_of_accounts_name  TEXT,
    category_confidence     FLOAT CHECK (category_confidence BETWEEN 0 AND 1),
    vendor_name             TEXT,
    tax_id                  TEXT,
    invoice_number          TEXT,
    bank_movement_id        UUID,
    fiscal_period           TEXT CHECK (fiscal_period ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    status                  TEXT NOT NULL DEFAULT 'pending_review'
                              CHECK (status IN ('pending_review','verified','closed')),
    -- FASE 2: quickbooks_id TEXT,
    metadata                JSONB NOT NULL DEFAULT '{}',
    extra                   JSONB NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ft_tenant_status ON financial_transactions (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_ft_tenant_period ON financial_transactions (tenant_id, fiscal_period);
CREATE INDEX IF NOT EXISTS idx_ft_tenant_date   ON financial_transactions (tenant_id, transaction_date DESC);

-- ── bank_movements ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bank_movements (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    bank_account_number     TEXT NOT NULL,
    bank_name               TEXT NOT NULL,
    movement_date           DATE NOT NULL,
    value_date              DATE,
    description             TEXT NOT NULL,
    reference               TEXT,
    debit_amount            NUMERIC(18,4) NOT NULL DEFAULT 0 CHECK (debit_amount >= 0),
    credit_amount           NUMERIC(18,4) NOT NULL DEFAULT 0 CHECK (credit_amount >= 0),
    running_balance         NUMERIC(18,4),
    currency                CHAR(3) NOT NULL DEFAULT 'USD',
    chart_of_accounts_code  TEXT,
    chart_of_accounts_name  TEXT,
    category_confidence     FLOAT CHECK (category_confidence BETWEEN 0 AND 1),
    matched_invoice_id      UUID,
    matched_transaction_id  UUID REFERENCES financial_transactions(id),
    status                  TEXT NOT NULL DEFAULT 'pending_review'
                              CHECK (status IN ('pending_review','verified','closed')),
    source_file_path        TEXT NOT NULL,
    statement_month         TEXT NOT NULL CHECK (statement_month ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    extra                   JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_bm_tenant_month ON bank_movements (tenant_id, statement_month);

-- ── monthly_ledgers ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS monthly_ledgers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    fiscal_period       TEXT NOT NULL CHECK (fiscal_period ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    currency            CHAR(3) NOT NULL DEFAULT 'USD',
    entries             JSONB NOT NULL DEFAULT '[]',
    transaction_count   INT NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    closed_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, fiscal_period)
);
CREATE INDEX IF NOT EXISTS idx_ml_tenant ON monthly_ledgers (tenant_id, fiscal_period);

-- ── chart_of_accounts (pgvector RAG) ────────────────────────
CREATE TABLE IF NOT EXISTS chart_of_accounts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN ('asset','liability','equity','income','expense','cogs')),
    description TEXT,
    embedding   vector(1536) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code)
);
CREATE INDEX IF NOT EXISTS idx_coa_embedding
    ON chart_of_accounts USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ── pgvector semantic search RPC ─────────────────────────────
CREATE OR REPLACE FUNCTION match_accounts(
    query_embedding vector(1536),
    p_tenant_id     UUID,
    match_threshold FLOAT,
    match_count     INT
)
RETURNS TABLE (id UUID, code TEXT, name TEXT, account_type TEXT, description TEXT, similarity FLOAT)
LANGUAGE sql STABLE AS $$
    SELECT id, code, name, account_type, description,
           1 - (embedding <=> query_embedding) AS similarity
    FROM   chart_of_accounts
    WHERE  tenant_id = p_tenant_id
      AND  1 - (embedding <=> query_embedding) > match_threshold
    ORDER  BY embedding <=> query_embedding
    LIMIT  match_count;
$$;
