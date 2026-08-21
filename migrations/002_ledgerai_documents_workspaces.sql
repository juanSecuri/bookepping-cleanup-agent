-- LedgerAI: documents, rejected status, workspace fields, CoA subcategory
-- Applied remotely as: ledgerai_documents_rejected_workspaces

CREATE TABLE IF NOT EXISTS documents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        UUID NOT NULL,
    file_name           TEXT NOT NULL,
    file_type           TEXT NOT NULL CHECK (file_type IN ('image','pdf','csv','audio','other')),
    file_size_bytes     INT,
    status              TEXT NOT NULL DEFAULT 'processing'
                          CHECK (status IN ('uploading','processing','extracted','failed')),
    extraction_confidence FLOAT,
    raw_extracted_text  TEXT,
    error_message       TEXT,
    document_date       DATE,
    vendor              TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_docs_workspace ON documents (workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_docs_workspace_status ON documents (workspace_id, status);
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

ALTER TABLE financial_transactions DROP CONSTRAINT IF EXISTS financial_transactions_status_check;
ALTER TABLE financial_transactions
  ADD CONSTRAINT financial_transactions_status_check
  CHECK (status IN ('pending_review','verified','closed','rejected'));

ALTER TABLE financial_transactions
  ADD COLUMN IF NOT EXISTS ai_suggested_account_code TEXT,
  ADD COLUMN IF NOT EXISTS ai_suggested_account_name TEXT,
  ADD COLUMN IF NOT EXISTS notes TEXT,
  ADD COLUMN IF NOT EXISTS reconciled BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE clients
  ADD COLUMN IF NOT EXISTS currency CHAR(3) NOT NULL DEFAULT 'USD',
  ADD COLUMN IF NOT EXISTS fiscal_year_start TEXT NOT NULL DEFAULT '01-01',
  ADD COLUMN IF NOT EXISTS industry TEXT,
  ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC',
  ADD COLUMN IF NOT EXISTS legal_name TEXT;

ALTER TABLE chart_of_accounts
  ADD COLUMN IF NOT EXISTS subcategory TEXT,
  ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
