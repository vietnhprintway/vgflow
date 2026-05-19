#!/usr/bin/env python3
"""B87 v4.65.0 — validate ${PHASE_DIR}/IMPLEMENTATION-NOTES.html.

Cross-checks against OVERRIDE-DEBT.md + .final-review/verdict.md gaps.
Stdlib only. Wired at commands/vg/_shared/build/close.md STEP 7.2.

Exit codes:
  0 → notes consistent with override-debt + verdict gaps
  1 → BLOCK: notes empty/insufficient when overrides or gaps exist
  2 → BLOCK: notes file malformed HTML or path resolution failed

Decision rules (B87):
  override_debt == 0 AND verdict_gaps == 0 → PASS (notes can be empty)
  override_debt  > 0 OR verdict_gaps  > 0 → MUST have ≥1 valid <article>
  Each <article> MUST have ≥1 non-N/A section among (what / why / tradeoff)
  Each non-N/A section MUST have ≥50 chars of substantive text

Overrides:
  --allow-shortfall            CLI escape for transitional phases
  CONTEXT.md `implementation_notes_waiver: true` per-phase opt-out
"""
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


# ---------------------------------------------------------------------------
# Path resolution — 3-tier fallback
# ---------------------------------------------------------------------------

def _resolve_repo_root() -> Path:
    import os
    env = os.environ.get("VG_REPO_ROOT") or os.environ.get("VG_PROJECT")
    if env:
        return Path(env).resolve()
    cwd = Path.cwd().resolve()
    for c in [cwd, *cwd.parents]:
        if (c / ".vg").exists() or (c / ".git").exists():
            return c
    return cwd


def _resolve_phase_dir(repo: Path, phase: str) -> Path | None:
    phases_dir = repo / ".vg" / "phases"
    if not phases_dir.exists():
        return None
    matches = list(phases_dir.glob(f"{phase}-*"))
    if not matches:
        try:
            major, _, rest = phase.partition(".")
            if major.isdigit() and len(major) == 1:
                normalized = f"0{major}.{rest}" if rest else f"0{major}"
                matches = list(phases_dir.glob(f"{normalized}-*"))
        except Exception:
            pass
    if matches:
        return matches[0]
    bare = phases_dir / phase
    if bare.is_dir():
        return bare
    return None


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

class NotesParser(HTMLParser):
    """Walks IMPLEMENTATION-NOTES.html and collects articles + per-section
    content lengths excluding <p class="na">N/A</p> markers.
    """

    SECTION_KEYS = ("what", "why", "tradeoff", "other")

    def __init__(self) -> None:
        super().__init__()
        self.articles: list[dict] = []
        self._current_article: dict | None = None
        self._current_section_key: str | None = None
        self._current_section_is_na: bool = False
        self._in_p: bool = False
        self._p_is_na: bool = False
        self._buffer: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        a = dict(attrs)
        if tag == "article":
            self._current_article = {k: 0 for k in self.SECTION_KEYS}
            self._current_article["_task_id"] = a.get("data-task-id", "")
            self._current_article["_category"] = a.get("data-category", "")
        elif tag == "section" and self._current_article is not None:
            cls = (a.get("class") or "").strip()
            if cls in self.SECTION_KEYS:
                self._current_section_key = cls
            else:
                self._current_section_key = None
        elif tag == "p" and self._current_section_key is not None:
            self._in_p = True
            cls = (a.get("class") or "").strip()
            self._p_is_na = (cls == "na")
            self._buffer = []

    def handle_endtag(self, tag) -> None:
        if tag == "article" and self._current_article is not None:
            self.articles.append(self._current_article)
            self._current_article = None
        elif tag == "section":
            self._current_section_key = None
        elif tag == "p" and self._in_p:
            if not self._p_is_na and self._current_section_key:
                text = "".join(self._buffer).strip()
                self._current_article[self._current_section_key] += len(text)
            self._in_p = False
            self._p_is_na = False
            self._buffer = []

    def handle_data(self, data) -> None:
        if self._in_p:
            self._buffer.append(data)


def parse_notes(path: Path) -> tuple[list[dict], list[str]]:
    if not path.exists():
        return [], [f"notes file missing: {path}"]
    try:
        body = path.read_text(encoding="utf-8")
    except Exception as e:
        return [], [f"notes file read error: {e}"]
    p = NotesParser()
    try:
        p.feed(body)
    except Exception as e:
        return [], [f"notes HTML parse error: {e}"]
    return p.articles, p.errors


# ---------------------------------------------------------------------------
# Cross-source counts
# ---------------------------------------------------------------------------

def count_override_debt(phase_dir: Path, repo_root: Path) -> int:
    """OVERRIDE-DEBT.md lives at repo .vg/OVERRIDE-DEBT.md (shared across
    phases). Count entries (lines starting with `- `).
    """
    candidates = [repo_root / ".vg" / "OVERRIDE-DEBT.md",
                  phase_dir / "OVERRIDE-DEBT.md"]
    total = 0
    for p in candidates:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lstrip().startswith("- "):
                total += 1
    return total


def count_verdict_gaps(phase_dir: Path) -> int:
    """Final-review verdict.md frontmatter `gaps:` count."""
    v = phase_dir / ".final-review" / "verdict.md"
    if not v.exists():
        return 0
    try:
        body = v.read_text(encoding="utf-8")
    except Exception:
        return 0
    fm_match = re.search(r"^---\s*\n(.*?)\n---", body, re.DOTALL | re.MULTILINE)
    if not fm_match:
        return 0
    fm = fm_match.group(1)
    gaps_match = re.search(r"^gaps:\s*\[(.*?)\]", fm, re.MULTILINE | re.DOTALL)
    if not gaps_match:
        list_match = re.search(r"^gaps:\s*\n((?:\s*-\s+.*\n)+)", fm, re.MULTILINE)
        if list_match:
            return sum(1 for ln in list_match.group(1).splitlines()
                       if ln.strip().startswith("-"))
        return 0
    inner = gaps_match.group(1).strip()
    if not inner:
        return 0
    return sum(1 for x in inner.split(",") if x.strip())


def context_waiver(phase_dir: Path) -> bool:
    ctx = phase_dir / "CONTEXT.md"
    if not ctx.exists():
        return False
    try:
        body = ctx.read_text(encoding="utf-8")
    except Exception:
        return False
    return bool(re.search(r"^implementation_notes_waiver:\s*true\s*$",
                          body, re.MULTILINE | re.IGNORECASE))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

MIN_SECTION_CHARS = 50


def evaluate(phase_dir: Path, repo_root: Path,
             allow_shortfall: bool) -> tuple[int, list[str]]:
    msgs: list[str] = []
    waiver = context_waiver(phase_dir)
    if waiver:
        msgs.append(f"✓ CONTEXT.md implementation_notes_waiver: true — skip")
        return 0, msgs

    notes_path = phase_dir / "IMPLEMENTATION-NOTES.html"
    notes_exists = notes_path.exists()
    if notes_exists:
        articles, parse_errs = parse_notes(notes_path)
    else:
        articles, parse_errs = [], []

    override_count = count_override_debt(phase_dir, repo_root)
    gap_count = count_verdict_gaps(phase_dir)
    msgs.append(
        f"counts: override_debt={override_count} verdict_gaps={gap_count} "
        f"articles={len(articles)} file_exists={notes_exists}"
    )

    # Genuine parse failure on EXISTING file → malformed → exit 2.
    # Missing file is NOT a parse error; semantic eval below decides.
    if notes_exists and parse_errs:
        msgs.extend(f"  parse: {e}" for e in parse_errs)
        return 2, msgs

    if override_count == 0 and gap_count == 0:
        msgs.append("✓ no overrides/gaps → notes can be empty → PASS")
        return 0, msgs

    valid_articles = []
    for art in articles:
        has_substantive = any(
            art.get(k, 0) >= MIN_SECTION_CHARS for k in ("what", "why", "tradeoff")
        )
        if has_substantive:
            valid_articles.append(art)

    if not valid_articles:
        if allow_shortfall:
            msgs.append(
                f"⚠ overrides/gaps exist but no valid articles; "
                f"--allow-shortfall set → PASS"
            )
            return 0, msgs
        msgs.append(
            f"⛔ override_debt={override_count} verdict_gaps={gap_count} > 0 "
            f"BUT no valid <article> in IMPLEMENTATION-NOTES.html. "
            f"AI MUST document at least one decision/tradeoff/deviation "
            f"per phase that has overrides or gaps. See template HTML comment "
            f"for append syntax. Pass --allow-shortfall to override."
        )
        return 1, msgs

    msgs.append(f"✓ {len(valid_articles)}/{len(articles)} articles valid → PASS")
    return 0, msgs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate IMPLEMENTATION-NOTES.html (B87)"
    )
    ap.add_argument("--phase", required=True)
    ap.add_argument("--phase-dir", default=None,
                    help="Override resolved phase dir")
    ap.add_argument("--allow-shortfall", action="store_true")
    args = ap.parse_args(argv)

    repo = _resolve_repo_root()
    if args.phase_dir:
        phase_dir = Path(args.phase_dir).resolve()
    else:
        phase_dir = _resolve_phase_dir(repo, args.phase)
    if phase_dir is None or not phase_dir.is_dir():
        print(f"⛔ phase dir not resolvable for phase={args.phase}",
              file=sys.stderr)
        return 2

    rc, msgs = evaluate(phase_dir, repo, args.allow_shortfall)
    for m in msgs:
        print(m, file=sys.stderr if rc != 0 else sys.stdout)
    return rc


if __name__ == "__main__":
    sys.exit(main())
