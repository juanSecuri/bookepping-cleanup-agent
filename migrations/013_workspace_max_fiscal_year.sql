-- Per-workspace CPA / ingest year ceiling (NULL = no cutoff; MyXcell uses 2025).
ALTER TABLE clients
  ADD COLUMN IF NOT EXISTS max_fiscal_year INT
  CHECK (max_fiscal_year IS NULL OR (max_fiscal_year >= 2000 AND max_fiscal_year <= 2100));

COMMENT ON COLUMN clients.max_fiscal_year IS
  'Keep/ingest only through this calendar year (inclusive). NULL = no year filter.';
