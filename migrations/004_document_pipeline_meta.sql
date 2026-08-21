-- Document pipeline visibility (kind, APIs, folder)

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS pipeline_kind TEXT,
  ADD COLUMN IF NOT EXISTS apis_used TEXT,
  ADD COLUMN IF NOT EXISTS folder_group TEXT;
