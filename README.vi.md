# VGFlow

> **Ngôn ngữ:** [Tiếng Việt](README.vi.md) · [English](README.md)

Pipeline phát triển AI config-driven cho Claude Code, Codex CLI và Gemini CLI. Zero hardcode giá trị stack — tất cả đến từ `vg.config.md`.

**Phiên bản:** 1.1.0 · **License:** MIT

---

## Pipeline (2 tầng)

### Tầng dự án (chạy 1 lần khi khởi tạo project / milestone)

```
/vg:project       →  /vg:roadmap   →  /vg:map          →  /vg:prioritize
(thảo luận           (ROADMAP.md,     (tuỳ chọn —          (phase nào
7 vòng →             danh sách        graphify              làm tiếp theo)
PROJECT.md +         phases, soft     codebase)
FOUNDATION.md +      drift warning)
vg.config.md
ATOMIC)
```

**v1.6.0 thay đổi entry point**: `/vg:project` là entry point duy nhất. Nó capture mô tả tự nhiên của user, derive FOUNDATION (8 chiều: platform/runtime/data/auth/hosting/distribution/scale/compliance), rồi auto-generate `vg.config.md`. Config là downstream của foundation, không phải upstream.

`/vg:init` còn giữ làm soft alias backward-compat → `/vg:project --init-only`.

### Tầng phase (7 bước)

```
/vg:specs  →  /vg:scope  →  /vg:blueprint  →  /vg:build  →  /vg:review  →  /vg:test  →  /vg:accept
(mục tiêu,    (thảo luận     (PLAN.md +         (wave-based     (scan + fix    (verify goal   (UAT
scope,        → CONTEXT.md   API-CONTRACTS +     parallel        loop →         + codegen     bằng người
constraints)  với D-XX)      TEST-GOALS)         execute)        RUNTIME-MAP)   regression)   → UAT.md)
```

Shortcut chạy full pipeline: `/vg:phase {X}` chạy cả 7 bước phase với resume support.
Advance step-by-step: `/vg:next` tự detect vị trí hiện tại + invoke command tiếp theo.

---

## Cài đặt (project mới)

```bash
cd /đường/dẫn/project
curl -fsSL https://raw.githubusercontent.com/vietdev99/vgflow/main/install.sh -o /tmp/vgflow-install.sh
bash /tmp/vgflow-install.sh .
```

Hoặc thủ công:
```bash
git clone https://github.com/vietdev99/vgflow.git /tmp/vgflow
bash /tmp/vgflow/install.sh /đường/dẫn/project
```

Script installer sẽ copy commands, skills, scripts, templates, và sinh `.claude/vg.config.md` từ template. Codex + Gemini CLI skills deploy vào `.codex/skills/` và `~/.codex/skills/` (global) nếu detect được.

## Cập nhật cho install có sẵn

```
/vg:update --check                   # peek phiên bản mới nhất không apply
/vg:update                           # apply release mới nhất
/vg:update --accept-breaking         # bắt buộc khi major version bump
/vg:reapply-patches                  # resolve conflicts từ /vg:update
```

Luồng update: query GitHub API → tải tarball + verify SHA256 → 3-way merge (giữ local edits của user) → park conflicts vào `.claude/vgflow-patches/`.

## Danh sách commands

### Khởi tạo project
| Command | Mục đích |
|---------|---------|
| `/vg:project` | **ENTRY POINT** — Thảo luận 7 vòng → PROJECT.md + FOUNDATION.md + vg.config.md (atomic) |
| `/vg:project --view` | In hiện trạng artifacts (read-only) |
| `/vg:project --update` | Update artifacts hiện có, MERGE preserve phần không touch |
| `/vg:project --milestone` | Append milestone mới (foundation untouched) |
| `/vg:project --rewrite` | Reset destructive với backup → `.archive/{ts}/` |
| `/vg:project --migrate` | Extract FOUNDATION.md từ legacy v1 PROJECT.md + scan codebase |
| `/vg:project --init-only` | Re-derive vg.config.md từ FOUNDATION.md hiện có |
| `/vg:init` | [DEPRECATED] Soft alias → `/vg:project --init-only` |
| `/vg:roadmap` | Derive phases từ PROJECT + FOUNDATION → ROADMAP.md (soft drift warning) |
| `/vg:map` | Rebuild graphify knowledge graph → `codebase-map.md` |
| `/vg:prioritize` | Rank phases theo impact + readiness |

### Phase execution (7-step pipeline)
| Bước | Command | Output |
|------|---------|--------|
| 1 | `/vg:specs {X}` | SPECS.md (goal, scope, constraints, success criteria) |
| 2 | `/vg:scope {X}` | CONTEXT.md (enriched với decisions D-XX) + DISCUSSION-LOG.md |
| 3 | `/vg:blueprint {X}` | PLAN.md + API-CONTRACTS.md + TEST-GOALS.md + CrossAI review |
| 4 | `/vg:build {X}` | Code + SUMMARY.md (wave-based parallel execution) |
| 5 | `/vg:review {X}` | RUNTIME-MAP.json (browser discovery + fix loop) |
| 6 | `/vg:test {X}` | SANDBOX-TEST.md (goal verification + codegen regression) |
| 7 | `/vg:accept {X}` | UAT.md (human acceptance) |

### Quản lý
| Command | Mục đích |
|---------|---------|
| `/vg:phase {X}` | Chạy full 7-step phase pipeline với resume support |
| `/vg:next` | Tự detect + advance step tiếp theo |
| `/vg:progress` | Status toàn bộ phases + check update |
| `/vg:amend {X}` | Mid-phase change — update CONTEXT.md, cascade impact |
| `/vg:add-phase` | Thêm phase mới vào ROADMAP.md |
| `/vg:remove-phase` | Archive + xoá phase |
| `/vg:regression` | Re-run tất cả tests từ các phases đã accept |
| `/vg:migrate {X}` | Convert legacy GSD artifacts sang VG format (cả backfill infra registers) |

### Distribution + infra
| Command | Mục đích |
|---------|---------|
| `/vg:update` | Kéo release mới nhất từ GitHub |
| `/vg:reapply-patches` | Resolve conflicts từ `/vg:update` |
| `/vg:sync` | Dev-side source↔mirror sync (chỉ dành cho maintainer) |
| `/vg:telemetry` | Summarize workflow telemetry |
| `/vg:security-audit-milestone` | Cross-phase security correlation |

## Cấu trúc repo

```
vgflow/
├── VERSION                   ← SemVer (vd "1.1.0")
├── CHANGELOG.md              ← curated mỗi release
├── commands/vg/              ← Claude Code slash commands
├── skills/                   ← api-contract, vg-* skills
├── codex-skills/             ← Codex CLI parity
├── gemini-skills/            ← Gemini CLI parity
├── scripts/                  ← Python helpers (vg_update, graphify, visual-diff, …)
├── templates/vg/             ← commit-msg hook template
├── vg.config.template.md     ← schema seed cho project mới
├── migrations/               ← vN_to_vN+1.md hướng dẫn breaking-change
├── install.sh                ← entrypoint cài đặt lần đầu
└── sync.sh                   ← dev-side source↔mirror (maintainer)
```

## Kênh phát hành

- **Tags:** SemVer — `v1.2.3`
- **Tarballs:** attach vào mỗi GitHub Release (auto-build qua `.github/workflows/release.yml`)
- **Changelog:** `CHANGELOG.md` + render trong body của mỗi Release
- **Breaking changes:** `migrations/vN_to_vN+1.md` hiển thị trước khi update proceed

## Đóng góp

Được maintain bởi [@vietdev99](https://github.com/vietdev99). Tạm thời không accept external PR — welcome bug report qua issues.

## License

MIT — xem [LICENSE](LICENSE)
