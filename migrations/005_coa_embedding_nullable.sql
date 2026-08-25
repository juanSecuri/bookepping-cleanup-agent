-- Allow CoA without paid OpenAI embeddings (local/free stack)

ALTER TABLE chart_of_accounts
  ALTER COLUMN embedding DROP NOT NULL;
