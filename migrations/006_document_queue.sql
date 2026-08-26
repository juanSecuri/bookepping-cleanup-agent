-- Document queue for Render Free (1-at-a-time processing)
-- Applied remotely as: document_queue_pending

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_status_check;
ALTER TABLE documents
  ADD CONSTRAINT documents_status_check
  CHECK (status IN ('pending', 'uploading', 'processing', 'extracted', 'failed'));

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS local_path TEXT,
  ADD COLUMN IF NOT EXISTS queue_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_docs_queue_pending
  ON documents (created_at ASC)
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_docs_queue_processing
  ON documents (processing_started_at ASC)
  WHERE status = 'processing';
