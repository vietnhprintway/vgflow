---
# Phase 0 diagnostic fixture — vg.config.md (DOCUMENTATION ONLY).
#
# CRITICAL FINDING from Task 2 inspection:
#   scripts/spawn-crud-roundtrip.py:213 reads `REPO_ROOT/.claude/vg.config.md`
#   (NOT phase_dir/vg.config.md and NOT phase_dir/.claude/vg.config.md).
#
# Therefore this file is NOT loaded by the dispatcher. It exists here only
# to document what the fixture would declare if the dispatcher honored
# phase-local config — and to make the design intent of this fixture
# explicit for future readers.
#
# See .diagnosis.md → Hypothesis H1/H6 analysis.

project_name: "phase0-diagnostic-smoke"
profile: "web-fullstack"

review:
  roles: ["admin", "user"]
  auth:
    base_url: "http://localhost:5555"
    login_endpoint: "POST /api/auth/login"
    seed_users_path: ".review-fixtures/seed-users.local.yaml"
    token_ttl_seconds: 3600
  crud_roundtrip:
    enabled: true
    cost_cap_usd: 0.10
    concurrency: 1
    worker_model: "gemini-2.5-flash"
    worker_mcp_server: "playwright1"
    worker_timeout_seconds: 60

base_url: "http://localhost:5555"
---
