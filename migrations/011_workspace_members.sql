-- Mirror of supabase/migrations/20260827120000_workspace_members.sql
-- Prefer applying the supabase/ path; this copy keeps the legacy migrations/ folder in sync.

CREATE TABLE IF NOT EXISTS workspace_members (
    user_id      UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES clients (id) ON DELETE CASCADE,
    role         TEXT NOT NULL DEFAULT 'member'
                   CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace
    ON workspace_members (workspace_id);

CREATE INDEX IF NOT EXISTS idx_workspace_members_user
    ON workspace_members (user_id);

ALTER TABLE workspace_members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS workspace_members_select_own ON workspace_members;
CREATE POLICY workspace_members_select_own
    ON workspace_members
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

COMMENT ON TABLE workspace_members IS
  'Maps Supabase auth.users to LedgerAI workspaces (clients.id). Enforced by FastAPI when AUTH_ENABLED=true.';
