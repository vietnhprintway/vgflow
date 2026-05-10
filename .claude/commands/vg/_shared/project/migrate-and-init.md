<step name="8_mode_migrate">
## Step 8 (mode=migrate): Extract foundation từ existing artifacts

Use case: project có sẵn PROJECT.md + vg.config.md cũ (no FOUNDATION.md). Cần slim PROJECT.md, sinh FOUNDATION.md từ data có sẵn.

```bash
# Confirm intent
echo "Migration: extract FOUNDATION.md từ existing PROJECT.md + scan codebase + vg.config.md"
echo "Backup PROJECT.md cũ → .archive/{ts}/PROJECT.v1.md"
```

Steps:
1. Read existing PROJECT.md, extract sections related to foundation (Tech Stack, Constraints, Architecture)
2. Scan codebase: `package.json`, `tsconfig.json`, framework manifests, `infra/`, `docker-compose.yml`, `.github/workflows/*.yml`
3. Read existing vg.config.md for already-confirmed config
4. Auto-derive 8 foundation dimensions (high confidence — codebase ground truth)
5. Show diff to user:
   ```
   ## Migration preview

   Will create: FOUNDATION.md (extracted)
   | Dimension | Source | Value |
   |-----------|--------|-------|
   | Platform | scan: apps/web/ React | web-saas |
   | Frontend | package.json: vite | React + Vite |
   | Backend | scan: apps/api/ Fastify | Fastify monolith |
   | ...

   PROJECT.md sẽ được slim down — di chuyển foundation fields ra FOUNDATION.md.
   Backup PROJECT.md cũ → ${PLANNING_DIR}/.archive/{ts}/PROJECT.v1.md
   ```
6. **⛔ forced user pause (destructive: rewrites PROJECT.md + creates FOUNDATION.md).**
   Invoke `AskUserQuestion`:
     - header: "Confirm migration"
     - question: "Tôi sẽ backup PROJECT.md hiện tại vào archive, tạo FOUNDATION.md mới, và slim down PROJECT.md (bỏ tech stack/architecture fields sang FOUNDATION). vg.config.md không đổi. Proceed?"
     - options:
       - "Yes — migrate (backup sẽ được giữ ở .archive/)"
       - "No — abort, PROJECT.md giữ nguyên"
   Không auto-proceed trên silence. Chỉ thực hiện migration khi user chọn Yes.
7. Nếu user chọn Yes:
   - Backup PROJECT.md → archive
   - Write FOUNDATION.md (new file)
   - Rewrite PROJECT.md (slim — keep identity/users/requirements/milestones, remove tech stack/architecture)
   - vg.config.md untouched (already exists, foundation matches)
   - Commit: `project(migrate): extract FOUNDATION.md from v1 PROJECT.md + codebase scan`
</step>

<step name="9_mode_init_only">
## Step 9 (mode=init_only): Re-derive vg.config.md from existing FOUNDATION.md

Use case: foundation OK nhưng vg.config.md outdated (vd: thêm crossai CLI, đổi model selection, port shift).

Required: FOUNDATION.md exists. If not → error: "FOUNDATION.md missing. Run /vg:project (no flag) trước."

```bash
if [ ! -f "$FOUNDATION_FILE" ]; then
  echo "⛔ FOUNDATION.md không tồn tại."
  echo "   /vg:project --init-only chỉ chạy được khi đã có foundation."
  echo "   Run /vg:project (first time) hoặc /vg:project --migrate trước."
  exit 1
fi
```

Re-run Round 6 only (config derivation). Show diff vs current vg.config.md.

**⛔ forced user pause (overwrites vg.config.md).**
Invoke `AskUserQuestion`:
  - header: "Apply config changes?"
  - question: "Đã diff xong vg.config.md cũ vs mới. Nếu Apply, tôi sẽ atomic overwrite vg.config.md và commit. Downstream commands sẽ dùng config mới ngay. Proceed?"
  - options:
    - "Apply — overwrite + commit"
    - "Abort — vg.config.md giữ nguyên"
Không auto-advance. Chỉ overwrite khi user chọn Apply.
</step>

<step name="10_complete">
## Step 10: Pipeline-state + next-step pointer

```bash
# Update PIPELINE-STATE.json at root level (not phase-specific)
PIPELINE_STATE="${PLANNING_DIR}/PIPELINE-STATE.json"
${PYTHON_BIN} - <<PY 2>/dev/null
import json
from pathlib import Path
import datetime
p = Path("${PIPELINE_STATE}")
s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
s["project_status"] = "ready"
s["foundation_locked_at"] = datetime.datetime.now().isoformat()
s["last_mode"] = "${MODE}"
p.write_text(json.dumps(s, indent=2), encoding="utf-8")
PY
```

Print next-step pointer based on mode:
- first_time / migrate / rewrite → "Next: /vg:roadmap"
- update / init_only → "Foundation/config updated. Re-check: /vg:progress"
- milestone → "Next: /vg:roadmap để add phases cho milestone"
- view → (no next step)
</step>
