"""v2.69.0 T1 — B1 spec-reviewer flip warn→block."""
import re
from pathlib import Path
import yaml


REPO_ROOT = Path(__file__).parent.parent


def test_b1_marker_no_longer_warn():
    body = (REPO_ROOT / "commands/vg/build.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", body, re.DOTALL)
    assert m, "frontmatter not found"
    fm = yaml.safe_load(m.group(1))

    markers = fm.get("runtime_contract", {}).get("must_touch_markers", [])
    spec_marker = next(
        (mk for mk in markers if isinstance(mk, dict) and mk.get("name") == "5_1_spec_compliance_review"),
        None
    )
    # After flip: should be string (hard) OR dict without severity:warn
    assert spec_marker is None or spec_marker.get("severity") != "warn", \
        f"5_1_spec_compliance_review still severity=warn (v2.69.0 must flip): {spec_marker}"


def test_b1_marker_in_required_unless_flag_form():
    """After flip: marker should be required_unless_flag --skip-spec-review (not severity:warn)."""
    body = (REPO_ROOT / "commands/vg/build.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", body, re.DOTALL)
    fm = yaml.safe_load(m.group(1))
    markers = fm.get("runtime_contract", {}).get("must_touch_markers", [])

    # Either string-form (hard required) OR dict with required_unless_flag
    spec_entry = next(
        (mk for mk in markers if (isinstance(mk, str) and "5_1_spec_compliance_review" in mk) or
         (isinstance(mk, dict) and mk.get("name") == "5_1_spec_compliance_review")),
        None
    )
    assert spec_entry is not None, "marker missing entirely"


def test_skip_spec_review_flag_documented():
    body = (REPO_ROOT / "commands/vg/build.md").read_text(encoding="utf-8")
    assert "--skip-spec-review" in body, "v2.69.0 must add --skip-spec-review escape hatch"


def test_skip_spec_review_in_forbidden_without_override():
    body = (REPO_ROOT / "commands/vg/build.md").read_text(encoding="utf-8")
    m = re.search(r"forbidden_without_override:.*?(?=\n[a-z]|\Z)", body, re.DOTALL)
    assert m and "--skip-spec-review" in m.group(0), \
        "--skip-spec-review must be in forbidden_without_override (debt-register tracked)"


def test_preflight_parses_skip_spec_review_flag():
    body = (REPO_ROOT / "commands/vg/_shared/build/preflight.md").read_text(encoding="utf-8")
    assert "--skip-spec-review" in body, "preflight parse loop must handle --skip-spec-review"
    # Should set SKIP_SPEC_REVIEW=1 + export
    assert re.search(r"SKIP_SPEC_REVIEW", body), "must set SKIP_SPEC_REVIEW env var"


def test_post_execution_skips_spec_reviewer_when_flag_set():
    body = (REPO_ROOT / "commands/vg/_shared/build/post-execution-overview.md").read_text(encoding="utf-8")
    # STEP 5.1 region must check SKIP_SPEC_REVIEW
    step5_1 = re.search(r"STEP 5\.1.*?(?=STEP 5\.|STEP 6|\Z)", body, re.DOTALL)
    assert step5_1, "STEP 5.1 section not found"
    assert "SKIP_SPEC_REVIEW" in step5_1.group(0), \
        "STEP 5.1 must short-circuit when SKIP_SPEC_REVIEW=1"
