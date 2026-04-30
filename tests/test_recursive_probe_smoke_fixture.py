"""Smoke test verifying recursive-probe-smoke fixture is well-formed."""
import json
import subprocess
import sys
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "recursive-probe-smoke"


def test_fixture_directory_exists():
    assert FIXTURE.is_dir()
    assert (FIXTURE / "scan-admin.json").is_file()
    assert (FIXTURE / "CRUD-SURFACES.md").is_file()
    assert (FIXTURE / ".phase-profile").is_file()


def test_scan_admin_json_well_formed():
    data = json.loads((FIXTURE / "scan-admin.json").read_text(encoding="utf-8"))
    assert data["view"] == "/admin/topup-requests"
    assert len(data["results"]) == 3
    assert len(data["forms"]) == 2


def test_phase_profile_eligible():
    """Profile must satisfy 6-rule eligibility (Task 18 will verify full)."""
    profile = yaml.safe_load((FIXTURE / ".phase-profile").read_text())
    assert profile["phase_profile"] == "feature"
    assert profile["surface"] == "ui"


def test_fixture_classifies_into_tier1():
    """identify_interesting_clickables.py finds expected element classes."""
    r = subprocess.run([
        sys.executable, "scripts/identify_interesting_clickables.py",
        "--scan-files", str(FIXTURE / "scan-admin.json"),
        "--json",
    ], capture_output=True, text=True, cwd=REPO_ROOT)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    classes = {c["element_class"] for c in out["clickables"]}
    expected = {"mutation_button", "form_trigger", "modal_trigger", "sub_view_link"}
    assert expected.issubset(classes), f"Missing: {expected - classes}"
