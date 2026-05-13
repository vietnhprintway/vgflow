"""tests/test_f7_domain_team_isolation.py — F7 domain/team schema + propagation."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]


def test_roadmap_template_documents_domain_team():
    tmpl_paths = [
        REPO / "templates" / "vg" / "ROADMAP.template.md",
        REPO / "commands" / "vg" / "_shared" / "templates" / "ROADMAP.template.md",
        REPO / "commands" / "vg" / "roadmap.md",
    ]
    found = False
    for p in tmpl_paths:
        if p.is_file():
            body = p.read_text(encoding="utf-8")
            if "domain" in body.lower() and "team" in body.lower():
                found = True
                break
    assert found, (
        "F7: ROADMAP template must document domain + team fields per phase. "
        "Required for 50+ phase, multi-team projects."
    )


def test_specs_preflight_reads_domain_from_roadmap():
    body = (REPO / "commands/vg/_shared/specs/preflight.md").read_text(encoding="utf-8")
    assert "domain" in body.lower(), (
        "F7: specs/preflight must propagate domain field from ROADMAP.md into "
        "PIPELINE-STATE.json so downstream phases + events can filter by domain"
    )


def test_pipeline_state_schema_documents_domain():
    """LIFECYCLE.md (or PIPELINE-STATE schema doc) must document domain/team."""
    paths_to_check = [
        REPO / "commands" / "vg" / "LIFECYCLE.md",
        REPO / "schemas" / "pipeline-state.schema.json",
    ]
    found_doc = False
    for p in paths_to_check:
        if p.is_file():
            body = p.read_text(encoding="utf-8")
            if "domain" in body.lower():
                found_doc = True
                break
    assert found_doc, (
        "F7: LIFECYCLE.md or pipeline-state schema must document domain/team fields"
    )
