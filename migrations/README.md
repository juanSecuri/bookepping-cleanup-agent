# LedgerAI — SQL migrations

Apply files in numeric order (`001` → `012`) via the **Supabase SQL editor** or your migration runner.

- **Canonical folder:** `migrations/` (copied in the Docker image).
- **`supabase/migrations/`** is not used by deploy; do not add duplicates here.

Each file is idempotent where possible (`IF NOT EXISTS`, `CREATE OR REPLACE`).
