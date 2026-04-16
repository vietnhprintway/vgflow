---
name: vg:init
description: Interactive setup — generate vg.config.md for current project
allowed-tools:
  - Read
  - Write
  - Bash
  - AskUserQuestion
---

<objective>
Generate `.claude/vg.config.md` via interactive Q&A. Asks 7-8 questions, writes config, commits.
Run this once per project to onboard the VG workflow.
</objective>

<process>

<step name="1_check_existing">
Check if `.claude/vg.config.md` already exists AND has `project_name` filled (not blank template).

If filled → ask:
```
vg.config.md already exists for "{project_name}".
1. View current config
2. Overwrite with fresh config
3. Cancel
```

If blank template or missing → proceed to questions.
</step>

<step name="2_questions">
Ask ONE question at a time. Save each answer immediately.

**Q1: Project**
```
Project name? (e.g., "MyApp", "E-Commerce Platform")
```
Follow up: `Short description? (1 sentence)`

**Q2: Package Manager**
```
Package manager?
1. pnpm
2. npm
3. yarn
4. bun
```

**Q2b: Profile (what kind of app is this?)**
```
Profile? — determines which pipeline steps and gates run.
Web:
  1. web-fullstack       — API + UI + shared backend
  2. web-frontend-only   — UI consuming an external API
  3. web-backend-only    — API/service, no UI
Mobile (see follow-up Qs Q2m-*):
  4. mobile-rn           — React Native / Expo (TS)
  5. mobile-flutter      — Flutter (Dart)
  6. mobile-native-ios   — Swift + SwiftUI/UIKit
  7. mobile-native-android — Kotlin + Jetpack Compose
  8. mobile-hybrid       — Capacitor / Ionic (wrap web)
Other:
  9. cli-tool
  10. library
```

Auto-detect helpers BEFORE showing the menu (best-effort hints, not a
hard override — user's answer always wins):
```bash
# RN / Expo
[ -f eas.json ]                       && echo "hint: mobile-rn (eas.json present)"
[ -f app.json ] && grep -q expo app.json 2>/dev/null \
                                       && echo "hint: mobile-rn (expo in app.json)"
[ -f react-native.config.js ]         && echo "hint: mobile-rn"
# Flutter
[ -f pubspec.yaml ] && grep -q flutter pubspec.yaml 2>/dev/null \
                                       && echo "hint: mobile-flutter"
# Native iOS
[ -d ios ] && ls ios/*.xcodeproj >/dev/null 2>&1 \
                                       && echo "hint: mobile-native-ios (or mobile-rn if RN bridge)"
# Native Android
[ -d android ] && [ -f android/settings.gradle ] && \
  [ ! -f package.json ] && echo "hint: mobile-native-android"
# Hybrid
[ -f capacitor.config.ts ] || [ -f capacitor.config.json ] || [ -f ionic.config.json ] \
                                       && echo "hint: mobile-hybrid"
```

**If user picks 4-8 (any mobile profile), ask the mobile-specific block
Q2m-1..Q2m-7 now, then continue at Q3. Otherwise skip to Q3 directly.**

---

### Mobile follow-up (only if profile ∈ mobile-*)

**Q2m-1: Target platforms**
```
Which platforms will the app ship to? (pick one or more — comma-separated)
  ios
  android
  macos       # only for mobile-native-ios / mobile-rn Catalyst
  web         # PWA side product — only for mobile-flutter / mobile-hybrid
Example: ios,android
```
Store as `mobile.target_platforms` (YAML array). Empty answer → BLOCK: "pick at least one".

**Q2m-2: Devices (names for review + test)**
Workflow does NOT pick devices. Names come from you — `xcrun simctl list`
for iOS, `emulator -list-avds` for Android. Empty = skip that platform.
```
iOS simulator name?   (e.g. "iPhone 15 Pro", or empty if no iOS target)
iOS OS version?       (e.g. "17.0")
Android emulator AVD? (e.g. "Pixel_7_API_34", or empty if no Android target)
Android OS version?   (e.g. "34")
```

**Q2m-3: E2E automation framework**
```
E2E framework? — Maestro recommended (cross-platform YAML flows).
  1. maestro                     (default; best for RN/Flutter/hybrid)
  2. appium                      (full WebDriver, heavier setup)
  3. detox                       (RN only)
  4. xcuitest_espresso           (native iOS + Android pair)
```
Also ask:
```
Flows directory (relative to repo)? (e.g. "e2e/flows")
Screenshots directory?              (e.g. "e2e/screenshots")
```

**Q2m-4: Deploy provider**
```
Primary deploy provider?
  1. fastlane     (cross-stack default)
  2. eas          (Expo/RN cloud)
  3. firebase     (Firebase App Distribution — internal QA)
  4. codemagic    (cloud CI)
  5. bitrise      (cloud CI)
  6. manual       (build IPA/APK only, distribute manually)
```
Auto-detect override:
```bash
if [ -f eas.json ] && [ "$PROVIDER_ANSWER" != "eas" ]; then
  echo "Detected eas.json — recommend switching provider to 'eas' (confirm y/n)"
  # if y → set provider=eas + eas_auto_detect=true
fi
```

**Q2m-5: iOS build fallback (only if target_platforms contains ios)**
Detect host OS:
```bash
HOST_OS=$(uname -s)
```
If `HOST_OS != Darwin`:
```
iOS build requires macOS. Your host is $HOST_OS.
Enable cloud fallback so /vg:test auto-switches to a cloud provider for iOS steps?
  Y (default — recommended)
  N — I will always build iOS on a separate Mac/CI
```
If Y → set `mobile.deploy.cloud_fallback_for_ios: true` +
`mobile.deploy.cloud_fallback_provider` defaults to `eas` (or provider
chosen in Q2m-4 if it's already a cloud provider).

If Darwin: skip this question (no fallback needed).

**Q2m-6: Signing**
```
iOS team ID env-var NAME (e.g. APPLE_TEAM_ID — NOT the 10-char ID itself)?
  Empty to skip (provider manages signing — e.g. EAS managed)
iOS cert source?
  1. fastlane_match
  2. manual
  3. eas_managed
Android keystore path env-var NAME (e.g. ANDROID_KEYSTORE_PATH)?
  Empty to skip
Cert expiry warn days? [default 30]
Cert expiry block days? [default 0 = block only if actually expired]
```

**Q2m-7: Gate paths (for the 5 V1 mobile gates)**
Ask each; empty = that file doesn't exist in this project (skip gate
for that path):
```
iOS Info.plist path?            (e.g. "ios/App/Info.plist")
Android Manifest path?          (e.g. "android/app/src/main/AndroidManifest.xml")
Expo app.json path?             (e.g. "app.json" — RN only; empty for non-RN)
iOS PrivacyInfo.xcprivacy path? (e.g. "ios/App/PrivacyInfo.xcprivacy")
Android data safety YAML path?  (e.g. ".planning/android-data-safety.yaml")
Bundle size budgets — iOS IPA MB [default 100], Android APK MB [default 50], AAB MB [default 80]
```

Save all answers under `mobile.*` keys matching the commented schema in
`vgflow/vg.config.template.md`. Uncomment the block before writing.

Back to shared Q3.

---

**Q3: Local Environment**

Auto-detect OS from current platform. Auto-detect shell.
Auto-set project_path from current working directory.
Ask for local health check URL if applicable:
```
Local health check URL? (e.g., "curl -sf http://localhost:3000/health")
Empty to skip.
```

**Q4: Remote/Sandbox Environment**
```
Do you have a remote server for sandbox testing?
1. Yes — I'll provide SSH details
2. No — sandbox = local (same machine)
```

If Yes:
```
SSH command to connect? (e.g., "ssh myserver", "ssh user@1.2.3.4")
```
```
Project path on remote? (e.g., "/home/user/myapp")
```
```
Process manager on remote?
1. PM2
2. Docker Compose
3. systemd
4. Custom
```

If user selects 1-3: set deploy_profile accordingly (pm2/docker/systemd). Profile provides restart/status/rollback commands automatically.

If user selects 4 (Custom): ask follow-up commands:
```
Custom deploy — I need 3 commands:
  Restart command? (e.g., "supervisorctl restart myapp")
  Status command? (e.g., "supervisorctl status myapp")  
  Rollback extra? (e.g., "supervisorctl stop myapp") — empty to skip
```

Then ask for all profiles:
```
Health check command on remote? (e.g., "curl -sf http://localhost:3000/health")
```

If No: copy local env config to sandbox, set deploy_profile to "custom".

**Q4b: Seed Data**
```
Seed data command? (runs before review/test to populate DB with test data)

Examples:
  pnpm seed                           # monorepo seed script
  node apps/api/src/seed/index.js     # direct seed runner
  python manage.py seed --env=test    # Django-style
  Empty to skip (no seed data needed).
```

If provided: set `environments.local.seed_command` and `environments.sandbox.seed_command`.
If empty: omit field (review.md + test.md will skip seed step silently).

**Q5: Services**
```
What services does your project need to check before testing?
Enter each as: name | check_command | required (true/false)

Examples:
  API | curl -sf http://localhost:3000/health | true
  PostgreSQL | pg_isready -h localhost | true
  Redis | redis-cli ping | false

Enter one per line. Empty line to finish.
```

Apply to both local and sandbox (user can edit config later for differences).

**Q6: Test Credentials**
```
Test credentials for E2E browser testing?
Enter each as: role | domain | email | password

Examples:
  admin | admin.example.com | admin@test.com | Admin123!
  user | app.example.com | user@test.com | User123!

Enter one per line. Empty line to skip (no E2E auth needed).
```

**Q7: AI CLIs for CrossAI**
```
AI CLIs available for multi-AI code review? (CrossAI)
Enter each as: name | command

Examples:
  Codex | codex exec -m gpt-5.4 "{prompt}"
  Gemini | cat {context} | gemini -m gemini-2.5-pro -p "{prompt}"
  Claude | cat {context} | claude --model sonnet -p "{prompt}"

Enter one per line. Empty line to skip (CrossAI disabled).
```

**Q8: Code Structure**
```
Where are your API routes? (relative path, e.g., "src/routes", "apps/api/src/modules")
Empty to skip.
```
```
Where are your web pages/components? (e.g., "src/pages", "apps/web/src/pages")
Empty to skip.
```

**Q9: Knowledge Graph (graphify)**
```
Use graphify knowledge graph for sibling/caller context?
Saves ~50% executor tokens by querying graph instead of dumping file content.
Builds graph from your codebase (one-time ~10-30 min, then incremental).

1. Yes — install + use (recommended, default)
2. No  — use grep-based fallback (current default behavior)
```

If user picks "1. Yes":

**Step Q9a: Detect Python 3.10+ availability**
```bash
PYTHON_BIN=""
for cmd in ${PYTHON_BIN} python; do
  if command -v "$cmd" >/dev/null 2>&1; then
    VER=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
    MAJOR=$(echo "$VER" | cut -d. -f1)
    MINOR=$(echo "$VER" | cut -d. -f2)
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
      PYTHON_BIN="$cmd"
      break
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "⚠ Python 3.10+ not found. Graphify requires Python 3.10+."
  echo "  Install: https://www.python.org/downloads/"
  echo "  Falling back to graphify.enabled=false. Re-run /vg:init after Python install."
  GRAPHIFY_CHOICE="no"
else
  echo "✓ Python detected: $PYTHON_BIN ($($PYTHON_BIN --version))"
  GRAPHIFY_CHOICE="yes"
fi
```

**Step Q9b: Install graphify (if Python OK)**
```bash
if [ "$GRAPHIFY_CHOICE" = "yes" ]; then
  echo "Installing graphifyy[mcp]..."
  $PYTHON_BIN -m pip install --user 'graphifyy[mcp]' 2>&1 | tail -5
  
  # Verify install
  if ! command -v graphify >/dev/null 2>&1; then
    echo "⚠ graphify CLI not in PATH after install."
    echo "  Add to PATH: $($PYTHON_BIN -m site --user-base)/bin (Linux/Mac) or %APPDATA%/Python/Scripts (Windows)"
    AskUserQuestion: "Continue with graphify.enabled=true anyway? (you'll need to fix PATH manually) [Y/n]"
  fi
  
  echo "Installing graphify Claude integration..."
  graphify install 2>&1 | tail -3
  
  # If user picked any Codex CLIs in Q7, also install Codex integration
  # NOTE: Codex graphify only used by /vg:review (not /vg:build) — skip for now per scope
fi
```

**Step Q9c: Write .graphifyignore**
```bash
if [ "$GRAPHIFY_CHOICE" = "yes" ] && [ ! -f .graphifyignore ]; then
  cat > .graphifyignore <<'EOF'
# Auto-generated by /vg:init — graphify exclude patterns
.planning/
.claude/
node_modules/
dist/
build/
target/
.next/
graphify-out/
test-results/
playwright-report/
*.generated.*
coverage/
EOF
  echo "✓ Wrote .graphifyignore"
fi
```

**Step Q9d: Detect source code + offer initial scan**
```bash
if [ "$GRAPHIFY_CHOICE" = "yes" ]; then
  # Detect any meaningful code files (TS/JS/Rust/Python/Go/Java/etc)
  CODE_COUNT=$(find . -type d \( -name node_modules -o -name .git -o -name dist -o -name target -o -name .next -o -name graphify-out \) -prune -o \
    -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.rs" -o -name "*.py" -o -name "*.go" -o -name "*.java" \) \
    -print 2>/dev/null | head -50 | wc -l)
  
  if [ "$CODE_COUNT" -gt 5 ]; then
    echo "✓ Detected $CODE_COUNT+ code files — graph build viable"
    AskUserQuestion: "Build graph now? (~10-30 min, uses Claude tokens to extract concepts) [Y/n]"
    
    if user picks Yes:
      echo "Building graph (this runs in foreground — output streams to terminal)..."
      graphify . 2>&1 | tail -20
      
      # Verify graph created
      if [ -f graphify-out/graph.json ]; then
        echo "✓ Graph built: $(wc -c < graphify-out/graph.json) bytes"
        # Check graph.json size — sanity check
        SIZE=$(stat -c%s graphify-out/graph.json 2>/dev/null || stat -f%z graphify-out/graph.json 2>/dev/null)
        if [ "$SIZE" -lt 1000 ]; then
          echo "⚠ Graph suspiciously small ($SIZE bytes). Check for graphify errors above."
        fi
      else
        echo "⚠ Graph build failed — graph.json not created."
        echo "  Manual rebuild: graphify ."
        echo "  /vg:build will use grep fallback until graph exists."
      fi
    else:
      echo "Graph build deferred. Run manually: graphify ."
      echo "Until built, /vg:build will use grep fallback."
  else
    echo "ℹ No code files detected yet — graph build skipped."
    echo "  After adding code: graphify .  (then /vg:build will auto-use graph)"
  fi
fi
```

Save final choice for step 3 (config generation):
- `GRAPHIFY_ENABLED = (GRAPHIFY_CHOICE == "yes" ? "true" : "false")`
- `GRAPHIFY_CODE_PRESENT = (CODE_COUNT > 5 ? "true" : "false")`
- `GRAPHIFY_GRAPH_BUILT = (graphify-out/graph.json exists ? "true" : "false")`
</step>

<step name="3_generate">
Build vg.config.md content from all answers.

Use the blank template from `.claude/vg.config.md` as structure, fill in values:
- project_name, project_description, package_manager
- **profile** from Q2b (one of the 10 valid values); if mobile-*, also set
  `target_platforms` (array) from Q2m-1.
- environments.local: detected OS, shell, project_path, deploy, test_runner
- environments.sandbox: from Q4 answers (or copy of local if no remote)
- deploy_profile: from Q4 process manager choice
- services: from Q5 (same for local and sandbox by default)
- credentials: from Q6 (sandbox only, local can be empty)
- crossai_clis: from Q7
- code_patterns: from Q8
- **graphify**: from Q9 (`enabled: ${GRAPHIFY_ENABLED}`, keep all other defaults from template)

- **mobile block** (ONLY if profile ∈ {mobile-rn, mobile-flutter, mobile-native-ios,
  mobile-native-android, mobile-hybrid}):
  - Uncomment the `mobile:` block in the template.
  - Fill from Q2m-1..Q2m-7 answers:
      * mobile.target_platforms (Q2m-1)
      * mobile.devices.ios.simulator_name/os_version (Q2m-2)
      * mobile.devices.android.emulator_name/os_version (Q2m-2)
      * mobile.e2e.framework/flows_dir/screenshots_dir (Q2m-3)
      * mobile.deploy.provider + eas_auto_detect (Q2m-4)
      * mobile.deploy.cloud_fallback_for_ios + cloud_fallback_provider (Q2m-5)
      * mobile.deploy.signing.* (Q2m-6)
      * mobile.gates.* paths and thresholds (Q2m-7)
  - mobile.stack.typecheck_cmd/build_cmd/test_unit_cmd: infer from profile:
      * mobile-rn:             typecheck="tsc --noEmit", test_unit="jest"
      * mobile-flutter:        typecheck="dart analyze", test_unit="flutter test"
      * mobile-native-ios:     typecheck="swift-format lint -r .", test_unit="xcodebuild test ..."
      * mobile-native-android: typecheck="./gradlew lint", test_unit="./gradlew testDebugUnitTest"
      * mobile-hybrid:         typecheck="tsc --noEmit", test_unit="jest" (wrap web stack)
    If user's project has a package.json `scripts` entry that matches these
    patterns, offer detected cmd instead.
  - mobile.design_handlers: default to the full mapping
    (fig→figma_mcp, stitch→stitch_export, pencil→pencil_dev_api,
     swift→swiftui_preview, kt→compose_preview, dart→flutter_widgetbook).
    User can trim later.
- **mobile block skip** (for web/cli/library profiles): leave the `mobile:`
  block commented in template. Do NOT write an empty `mobile: {}` because
  downstream commands branch on its presence.

**⛔ Schema validation BEFORE preview (tightened 2026-04-17):**

Validate required fields and enum values. Show validation errors before asking user approval — typos in config propagate silently and break every downstream command.

```bash
# Write candidate to temp for validation
echo "$CONFIG_CONTENT" > "${VG_TMP:-/tmp}/vg.config.candidate.md"

VALIDATION_ERRORS=""

# Required fields (must be present with non-empty value)
for field in project_name package_manager profile; do
  if ! grep -qE "^${field}:\s*['\"]?[^'\"#\s].*" "${VG_TMP:-/tmp}/vg.config.candidate.md"; then
    VALIDATION_ERRORS="${VALIDATION_ERRORS}\n  - ${field}: missing or empty"
  fi
done

# Enum validation
PKG_MGR=$(grep -oE "^package_manager:\s*['\"]?[a-z]+" "${VG_TMP:-/tmp}/vg.config.candidate.md" | sed "s/package_manager:\s*['\"]*//")
case "$PKG_MGR" in
  pnpm|npm|yarn|bun) ;;
  *) VALIDATION_ERRORS="${VALIDATION_ERRORS}\n  - package_manager: '${PKG_MGR}' not in {pnpm|npm|yarn|bun}" ;;
esac

# Profile enum + mobile block consistency
PROFILE=$(grep -oE "^profile:\s*['\"]?[a-z-]+" "${VG_TMP:-/tmp}/vg.config.candidate.md" | sed "s/profile:\s*['\"]*//")
case "$PROFILE" in
  web-fullstack|web-frontend-only|web-backend-only|cli-tool|library) ;;
  mobile-rn|mobile-flutter|mobile-native-ios|mobile-native-android|mobile-hybrid)
    # mobile profile must have `mobile:` block uncommented
    if ! grep -qE '^mobile:' "${VG_TMP:-/tmp}/vg.config.candidate.md"; then
      VALIDATION_ERRORS="${VALIDATION_ERRORS}\n  - profile='${PROFILE}' but mobile: block missing (required for mobile profiles)"
    fi
    # target_platforms must be non-empty array
    if ! grep -qE '^target_platforms:\s*\[[^]]+\]' "${VG_TMP:-/tmp}/vg.config.candidate.md" \
       && ! grep -qE '^\s+target_platforms:\s*\[[^]]+\]' "${VG_TMP:-/tmp}/vg.config.candidate.md"; then
      VALIDATION_ERRORS="${VALIDATION_ERRORS}\n  - target_platforms: empty (pick at least one: ios/android/macos/web)"
    fi
    ;;
  *)
    VALIDATION_ERRORS="${VALIDATION_ERRORS}\n  - profile: '${PROFILE}' not in {web-fullstack|web-frontend-only|web-backend-only|cli-tool|library|mobile-rn|mobile-flutter|mobile-native-ios|mobile-native-android|mobile-hybrid}"
    ;;
esac

# Nested path validation (use Python for reliable YAML traversal if available)
${PYTHON_BIN:-python3} - <<PY >> "${VG_TMP:-/tmp}/validation.errors"
import re, sys
c = open("${VG_TMP:-/tmp}/vg.config.candidate.md", encoding='utf-8').read()
# environments.local.deploy.health must exist
if not re.search(r'environments:.*?local:.*?deploy:.*?health:', c, re.DOTALL):
    print("  - environments.local.deploy.health: missing (required for health checks)")
PY

[ -s "${VG_TMP:-/tmp}/validation.errors" ] && VALIDATION_ERRORS="${VALIDATION_ERRORS}\n$(cat ${VG_TMP:-/tmp}/validation.errors)"

if [ -n "$VALIDATION_ERRORS" ]; then
  echo "⛔ Config validation FAILED:"
  echo -e "$VALIDATION_ERRORS"
  echo ""
  echo "Fix these before preview. Do NOT write invalid config."
  # Loop back to offer re-answer
fi
```

Show preview to user ONLY if validation passed:
```
--- vg.config.md Preview ---
{full content}
--- End Preview ---

Write this config? (y/edit/n)
- y: Write file and commit
- edit: Tell me what to change
- n: Discard
```

If "edit": ask what to change, regenerate, re-validate, show again.
If "n": stop.
If "y": proceed to write.
</step>

<step name="4_write_and_commit">
Write to `.claude/vg.config.md` (overwrite blank template).

**Deploy commit-msg hook** (Phase 3D — enforces commit format + contract citation):

```bash
# Only if template exists in this project (skip silently for older VG installs)
if [ -f ".claude/templates/vg/commit-msg" ]; then
  mkdir -p .git/hooks
  cp .claude/templates/vg/commit-msg .git/hooks/commit-msg
  chmod +x .git/hooks/commit-msg 2>/dev/null || true
  echo "Installed .git/hooks/commit-msg — enforces pattern from vg.config.md commit_msg_hook section."
  echo "To disable: set commit_msg_hook.enabled=false in vg.config.md, or delete the hook."
fi
```

```bash
git add .claude/vg.config.md
git commit -m "chore(vg): init project config — ${PROJECT_NAME}"
```

Display:
```
VG config created: .claude/vg.config.md

Prerequisite (before pipeline):
  /vg:specs {X}         — Create SPECS.md (phase goal + scope + constraints)

Available commands:
  /vg:phase {X}         — Full V5 6-step pipeline (scope→blueprint→build→review→test→accept)
  /vg:scope {X}         — Step 1: Guided scope discussion → CONTEXT.md
  /vg:blueprint {X}     — Step 2: Plan + API contracts + TEST-GOALS (auto-triggers design-extract)
  /vg:build {X}         — Step 3: Contract-aware wave execution → SUMMARY*.md
  /vg:review {X}        — Step 4: Code scan + browser discovery + fix loop → RUNTIME-MAP
  /vg:test {X}          — Step 5: Deploy + goal verify + codegen regression → SANDBOX-TEST
  /vg:accept {X}        — Step 6: Human UAT acceptance
  /vg:next              — Auto-detect current step + advance
  /vg:progress          — Status across all phases
  /vg:init              — Re-run this setup
```
</step>

</process>

<success_criteria>
- `.claude/vg.config.md` written with all sections populated
- User approved the content before writing
- Git committed
- All environments, services, credentials reflect user answers
</success_criteria>
