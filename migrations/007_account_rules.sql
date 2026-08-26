-- Deterministic CoA rules + suspense account (Sprint account_rules)
-- Applied remotely as: account_rules_suspense

CREATE TABLE IF NOT EXISTS account_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    keywords        TEXT[] NOT NULL DEFAULT '{}',
    account_code    TEXT NOT NULL,
    account_name    TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'seed'
                      CHECK (source IN ('seed', 'learned', 'manual')),
    hit_count       INT NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_account_rules_tenant
  ON account_rules (tenant_id, is_active);

CREATE INDEX IF NOT EXISTS idx_account_rules_keywords
  ON account_rules USING GIN (keywords);

-- Rename suspense / uncategorized for auditor-friendly label
UPDATE chart_of_accounts
SET name = 'Gastos No Categorizados (Suspense)',
    subcategory = 'Suspense',
    description = 'Cuenta temporal cuando no hay regla CoA; el usuario corrige y se aprende la keyword.'
WHERE code = '9999';

ALTER TABLE account_rules ENABLE ROW LEVEL SECURITY;
