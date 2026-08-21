-- Drive sync fields (applied remotely as drive_sync_fields)

ALTER TABLE clients ADD COLUMN IF NOT EXISTS drive_folder_id TEXT;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS drive_folder_name TEXT;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS drive_file_id TEXT,
  ADD COLUMN IF NOT EXISTS drive_path TEXT,
  ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'upload';

CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_drive_file
  ON documents (workspace_id, drive_file_id)
  WHERE drive_file_id IS NOT NULL;
