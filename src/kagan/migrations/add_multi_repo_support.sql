-- ============================================================================
-- MIGRATION: Add Multi-Repo Support
-- ============================================================================

-- 1. Repos table needs display_name and default_working_dir columns (already exists but needs updates)
-- Note: repos table already exists with: id, project_id, name, path, default_branch, scripts, created_at, updated_at
-- We need to add: display_name, default_working_dir, and make path UNIQUE

-- 2. Project-Repos junction table
CREATE TABLE IF NOT EXISTS project_repos (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    repo_id TEXT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    is_primary BOOLEAN DEFAULT FALSE,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, repo_id)
);

-- 3. Workspace-Repos junction table
CREATE TABLE IF NOT EXISTS workspace_repos (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    repo_id TEXT NOT NULL REFERENCES repos(id),
    target_branch TEXT NOT NULL,
    worktree_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, repo_id)
);

-- 4. Add last_opened_at to projects for recent list
ALTER TABLE projects ADD COLUMN last_opened_at TIMESTAMP;

-- 5. Add repo_id to merges (merges are now per-repo within a workspace)
ALTER TABLE merges ADD COLUMN repo_id TEXT REFERENCES repos(id);

-- 6. Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_project_repos_project ON project_repos(project_id);
CREATE INDEX IF NOT EXISTS idx_project_repos_repo ON project_repos(repo_id);
CREATE INDEX IF NOT EXISTS idx_workspace_repos_workspace ON workspace_repos(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_repos_repo ON workspace_repos(repo_id);
CREATE INDEX IF NOT EXISTS idx_repos_path ON repos(path);
CREATE INDEX IF NOT EXISTS idx_projects_last_opened ON projects(last_opened_at DESC);
