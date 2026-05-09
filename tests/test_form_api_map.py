"""F3 v2.62.0: FORM-API-MAP generator + verifier — fix D4 form-field ↔ API drift."""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GEN = REPO_ROOT / "scripts" / "blueprint-form-api-map.py"
VERIFY = REPO_ROOT / "scripts" / "validators" / "verify-form-api-field-match.py"


def _setup_phase(tmp_path: Path, phase: str = "1.0", forms_html: str | None = None,
                 api_contract: str | None = None):
    phase_dir = tmp_path / ".vg" / "phases" / phase
    (phase_dir / "design" / "refs").mkdir(parents=True)
    (phase_dir / "design" / "screenshots").mkdir(parents=True)
    (phase_dir / "API-CONTRACTS").mkdir(parents=True)

    if forms_html:
        (phase_dir / "design" / "refs" / "login.structural.html").write_text(
            forms_html, encoding="utf-8",
        )
    if api_contract:
        (phase_dir / "API-CONTRACTS" / "auth-login.md").write_text(
            api_contract, encoding="utf-8",
        )

    (phase_dir / "design" / "manifest.json").write_text(
        json.dumps({"slugs": [{"slug": "login"}]}), encoding="utf-8",
    )
    return phase_dir


def test_generator_match_clean(tmp_path):
    """Form fields match API contract → no drift."""
    forms_html = textwrap.dedent('''
        <form action="/auth/login" method="POST" id="login-form">
          <input name="user_email" type="email" required>
          <input name="password" type="password" required>
        </form>
    ''').strip()
    api_contract = textwrap.dedent('''
        # POST /auth/login
        ## BLOCK 1: request schema
        ```typescript
        {
          user_email: string,
          password: string,
        }
        ```
    ''').strip()
    phase_dir = _setup_phase(tmp_path, "1.0", forms_html, api_contract)
    r = subprocess.run(
        [sys.executable, str(GEN), "--phase", "1.0", "--phase-dir", str(phase_dir)],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert r.returncode == 0, r.stderr
    map_file = phase_dir / "FORM-API-MAP.md"
    assert map_file.exists()
    body = map_file.read_text(encoding="utf-8")
    assert "# Form ↔ API field map" in body
    assert "login-form" in body
    assert "user_email" in body
    assert "✓" in body  # clean match marker


def test_generator_detects_name_drift(tmp_path):
    """Form name differs from API field → NAME-DRIFT row."""
    forms_html = textwrap.dedent('''
        <form action="/users" method="POST" id="signup">
          <input name="display_name" type="text" required>
        </form>
    ''').strip()
    api_contract = textwrap.dedent('''
        # POST /users
        ## BLOCK 1: request schema
        ```typescript
        {
          displayName: string,
        }
        ```
    ''').strip()
    phase_dir = _setup_phase(tmp_path, "2.0", forms_html, api_contract)
    r = subprocess.run(
        [sys.executable, str(GEN), "--phase", "2.0", "--phase-dir", str(phase_dir)],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert r.returncode == 0, r.stderr  # WARN by default, not BLOCK
    map_body = (phase_dir / "FORM-API-MAP.md").read_text(encoding="utf-8")
    assert "NAME-DRIFT" in map_body or "drift" in map_body.lower()


def test_generator_strict_blocks_on_drift(tmp_path):
    """--strict flag turns drift into BLOCK (rc=1)."""
    forms_html = '<form action="/x" method="POST"><input name="a_b"></form>'
    api_contract = '## BLOCK 1\n```typescript\n{ aB: string }\n```'
    phase_dir = _setup_phase(tmp_path, "3.0", forms_html, api_contract)
    r = subprocess.run(
        [sys.executable, str(GEN), "--phase", "3.0",
         "--phase-dir", str(phase_dir), "--strict"],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert r.returncode == 1, "strict mode must BLOCK on drift"


def test_generator_skip_forms_without_action(tmp_path):
    """Forms with no action= (client-side only) skipped."""
    forms_html = '<form id="search"><input name="q"></form>'
    phase_dir = _setup_phase(tmp_path, "4.0", forms_html, None)
    r = subprocess.run(
        [sys.executable, str(GEN), "--phase", "4.0", "--phase-dir", str(phase_dir)],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert r.returncode == 0
    body = (phase_dir / "FORM-API-MAP.md").read_text(encoding="utf-8")
    # Should mention no mappable forms or skip the search form
    assert "search" not in body or "skipped" in body.lower()


def test_verifier_no_drift_passes(tmp_path):
    """When FE code matches FORM-API-MAP expectations → rc=0, no evidence."""
    phase_dir = _setup_phase(tmp_path, "5.0", None, None)
    map_file = phase_dir / "FORM-API-MAP.md"
    map_file.write_text(textwrap.dedent('''
        # Form ↔ API field map — Phase 5.0

        ## login-form (from login)

        | HTML name attr | HTML type | required | pattern | API field | API type | Match |
        |---|---|---|---|---|---|---|
        | user_email | email | yes | — | user_email | string | ✓ |
    ''').strip(), encoding="utf-8")

    fe_root = tmp_path / "fe"
    fe_root.mkdir()
    (fe_root / "Login.tsx").write_text(
        '<form><input name="user_email" type="email"></form>',
        encoding="utf-8",
    )

    r = subprocess.run(
        [sys.executable, str(VERIFY), "--phase", "5.0",
         "--phase-dir", str(phase_dir), "--fe-root", str(fe_root)],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert r.returncode == 0


def test_verifier_drift_warn_default(tmp_path):
    """FE code uses different name than FORM-API-MAP expectation → WARN evidence (rc=0 default)."""
    phase_dir = _setup_phase(tmp_path, "6.0", None, None)
    (phase_dir / "FORM-API-MAP.md").write_text(textwrap.dedent('''
        # Form ↔ API field map — Phase 6.0
        ## login-form
        | HTML name attr | HTML type | required | pattern | API field | API type | Match |
        |---|---|---|---|---|---|---|
        | user_email | email | yes | — | user_email | string | ✓ |
    ''').strip(), encoding="utf-8")

    fe_root = tmp_path / "fe"
    fe_root.mkdir()
    (fe_root / "Login.tsx").write_text(
        '<form><input name="email" type="email"></form>',  # DRIFT: email vs user_email
        encoding="utf-8",
    )

    evidence_path = tmp_path / "evidence.json"
    r = subprocess.run(
        [sys.executable, str(VERIFY), "--phase", "6.0",
         "--phase-dir", str(phase_dir), "--fe-root", str(fe_root),
         "--evidence-out", str(evidence_path)],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    # Default mode: drift = WARN, rc=0; evidence file emitted
    assert r.returncode == 0
    assert evidence_path.exists()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    # Evidence shape: at least one mismatch entry
    assert evidence.get("severity") in ("warn", "WARN")
    assert "user_email" in json.dumps(evidence) or "email" in json.dumps(evidence)


def test_verifier_strict_blocks(tmp_path):
    """--strict flag turns drift into BLOCK (rc=1)."""
    phase_dir = _setup_phase(tmp_path, "7.0", None, None)
    (phase_dir / "FORM-API-MAP.md").write_text(textwrap.dedent('''
        # Form ↔ API field map — Phase 7.0
        ## login-form
        | HTML name attr | HTML type | required | pattern | API field | API type | Match |
        |---|---|---|---|---|---|---|
        | user_email | email | yes | — | user_email | string | ✓ |
    ''').strip(), encoding="utf-8")

    fe_root = tmp_path / "fe"
    fe_root.mkdir()
    (fe_root / "Login.tsx").write_text('<input name="email">', encoding="utf-8")

    r = subprocess.run(
        [sys.executable, str(VERIFY), "--phase", "7.0",
         "--phase-dir", str(phase_dir), "--fe-root", str(fe_root), "--strict"],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert r.returncode == 1, "strict mode must BLOCK on FE drift"


def test_blueprint_md_declares_form_api_map():
    body = (REPO_ROOT / "commands" / "vg" / "blueprint.md").read_text(encoding="utf-8")
    assert "FORM-API-MAP.md" in body, (
        "blueprint.md must declare FORM-API-MAP.md in must_write (F3 v2.62.0)"
    )


def test_generator_mirror():
    canonical = REPO_ROOT / "scripts" / "blueprint-form-api-map.py"
    mirror = REPO_ROOT / ".claude" / "scripts" / "blueprint-form-api-map.py"
    if not mirror.exists():
        return
    assert canonical.read_bytes() == mirror.read_bytes()


def test_verifier_mirror():
    canonical = REPO_ROOT / "scripts" / "validators" / "verify-form-api-field-match.py"
    mirror = REPO_ROOT / ".claude" / "scripts" / "validators" / "verify-form-api-field-match.py"
    if not mirror.exists():
        return
    assert canonical.read_bytes() == mirror.read_bytes()


def test_blueprint_md_mirror():
    canonical = REPO_ROOT / "commands" / "vg" / "blueprint.md"
    mirror = REPO_ROOT / ".claude" / "commands" / "vg" / "blueprint.md"
    if not mirror.exists():
        return
    assert canonical.read_bytes() == mirror.read_bytes()
