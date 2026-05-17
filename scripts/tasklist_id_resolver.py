"""tasklist_id_resolver.py — B71a: layered matcher for TodoWrite display labels → contract step_id.

Pure stdlib resolver. Used by:
  - scripts/hooks/vg-post-tool-use-todowrite.sh — at snapshot-write time, before
    payload reaches vg-tasklist-snapshot.py. Resolves the AI's free-form
    display labels (e.g. "↳ 0 Parse And Validate", "↳ test-spec 3_crossai_sweep")
    back to canonical contract step_ids (e.g. "0_parse_and_validate").
  - scripts/emit-tasklist.py:_restore_mode — at restore time for legacy v1
    snapshots that lack the `content` field, rehydrate via .taskcreate-trace.jsonl
    and run subjects through this resolver.

Pipeline (deterministic, layered, fail-closed on ambiguity):
  1. exact         — label == step_id literally.
  2. normalized    — strip leading `↳ `, lowercase, collapse whitespace,
                     replace `-` and `_` with space → token-equal to step_id slug.
  3. strip-cmd     — strip leading command prefix (`test-spec `, `build `, etc.).
  4. strip-decimal — `3.5 X` → also try `3_X` (drop fractional sub-step).
  5. substring     — contract step_id appears as substring of normalized label.
  6. slug          — slugify label → token-equal to step_id.
  7. unresolved    — return ("<unresolved>:" + 8-char hash, "unresolved").

Tie-breaks: prefer kind=step over kind=group; smaller Levenshtein distance.
If still ambiguous, fail-closed (return unresolved).

Status-conflict precedence (applied by caller when multiple labels resolve to
same step_id with different statuses): in_progress > completed > pending.

Schema (v2 .todowrite-snapshot.json):
  {
    "schema_version": 2,
    "items": [{"id": step_id, "content": original_label, "status": ...,
               "match_class": <one of 6 above>}],
    "id_map_provenance": {"contract_path": "...", "contract_hash": "sha256:...",
                          "resolved_at": "ISO8601"}
  }

STEP_ID_ALIASES: versioned dict mapping legacy step_ids to current.
  Example: {"step5_fix_loop": "5_fix_loop"}.
  Used by emit-tasklist.py:_write_contract merge logic when filter-steps.py
  output renames a step across versions.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Literal, Optional

MatchClass = Literal[
    "exact",
    "normalized",
    "strip-cmd",
    "strip-decimal",
    "substring",
    "slug",
    "unresolved",
]

# Command prefixes that AIs sometimes prepend to step labels.
# Order matters: longest first to avoid partial strip.
_CMD_PREFIXES = (
    "test-spec ",
    "scope-review ",
    "design-extract ",
    "design-reverse ",
    "design-system ",
    "review-batch ",
    "accept ",
    "amend ",
    "build ",
    "debug ",
    "deploy ",
    "field-test ",
    "init ",
    "install ",
    "learn ",
    "lesson ",
    "next ",
    "phase ",
    "polish ",
    "project ",
    "review ",
    "roam ",
    "scope ",
    "specs ",
    "test ",
    "validate ",
    "verify ",
)

# Legacy step ID aliases — current step_id → list of historical aliases.
# When filter-steps.py output renames a step, add the old name here so
# contract merge (B71c) can migrate statuses.
STEP_ID_ALIASES: dict[str, list[str]] = {
    # Examples (placeholder until first real rename lands):
    # "5_fix_loop": ["step5_fix_loop"],
    # "7_matrix_verdict": ["step7_matrix_verdict"],
}


def _normalize(label: str) -> str:
    """Lowercase + NFKD unicode normalize + strip leading `↳ ` + collapse whitespace +
    replace - and _ with space."""
    if not label:
        return ""
    # NFKD then strip combining marks for ASCII-only comparison robustness.
    nfkd = unicodedata.normalize("NFKD", label)
    ascii_form = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    s = ascii_form.lower().strip()
    # Strip leading bullet markers and arrows.
    s = re.sub(r"^[\s↳→↗↪>•\-*]+\s*", "", s)
    s = s.replace("—", "-").replace("–", "-")  # em/en dash → hyphen
    # Replace dashes/underscores with spaces, collapse runs of whitespace.
    s = re.sub(r"[-_]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _slugify(label: str) -> str:
    """Slugify: normalize → strip non-alnum-or-space → collapse spaces → join with _."""
    n = _normalize(label)
    n = re.sub(r"[^a-z0-9\s]", "", n)
    return "_".join(p for p in n.split() if p)


def _strip_cmd_prefix(normalized_label: str) -> Optional[str]:
    """If label starts with a known command prefix, return the remainder; else None."""
    for prefix in _CMD_PREFIXES:
        if normalized_label.startswith(prefix):
            return normalized_label[len(prefix):].strip()
    return None


def _strip_decimal(normalized_label: str) -> Optional[str]:
    """`3.5 x` → `3 x`. Returns transformed string or None if no decimal pattern."""
    m = re.match(r"^(\d+)\.\d+(\s+.*)?$", normalized_label)
    if not m:
        return None
    return (m.group(1) + (m.group(2) or "")).strip()


def _label_to_slug(label: str) -> str:
    """Snake_case slug suitable for direct step_id comparison.

    `↳ 0 Parse And Validate` → `0_parse_and_validate`.
    `↳ test-spec 3_crossai_sweep` → `test_spec_3_crossai_sweep`.
    """
    return _slugify(label)


def _levenshtein(a: str, b: str) -> int:
    """Standard iterative Levenshtein distance."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(
                cur[j - 1] + 1,
                prev[j] + 1,
                prev[j - 1] + (ca != cb),
            )
        prev = cur
    return prev[-1]


def _hash_id(label: str) -> str:
    """8-char hex hash for unresolved tagging."""
    return hashlib.sha256(label.encode("utf-8")).hexdigest()[:8]


def resolve(
    label: str,
    contract_items: list[dict],
    kind_hint: Optional[str] = None,
) -> tuple[str, MatchClass]:
    """Resolve a free-form display label to a contract step_id.

    Args:
        label: The AI's TodoWrite content / display label.
                Examples: "↳ 0 Parse And Validate", "step5_fix_loop",
                "↳ test-spec 3_crossai_sweep".
        contract_items: List of dicts with "id" key (step_id), optional "kind"
                ("step" or "group"), optional "title".
        kind_hint: If caller knows label was emitted as group vs step header,
                pass "group" or "step" to bias tie-break.

    Returns:
        (step_id, match_class). On unresolved, step_id is "<unresolved>:" + 8-char hash.
    """
    if not label:
        return (f"<unresolved>:empty", "unresolved")
    if not contract_items:
        return (f"<unresolved>:{_hash_id(label)}", "unresolved")

    contract_ids = {it.get("id") for it in contract_items if it.get("id")}
    if not contract_ids:
        return (f"<unresolved>:{_hash_id(label)}", "unresolved")

    # Index by kind for tie-break.
    kind_by_id = {it.get("id"): it.get("kind", "step") for it in contract_items}

    candidates: list[tuple[str, MatchClass]] = []

    # Layer 1 — exact.
    if label in contract_ids:
        return (label, "exact")

    # Normalize once.
    normalized = _normalize(label)

    # Layer 2 — normalized comparison against step_ids (slug them too).
    for cid in contract_ids:
        cid_norm = _normalize(cid)
        if normalized == cid_norm:
            candidates.append((cid, "normalized"))

    # Layer 3 — strip command prefix and recompare.
    stripped_cmd = _strip_cmd_prefix(normalized)
    if stripped_cmd and stripped_cmd != normalized:
        for cid in contract_ids:
            if _normalize(cid) == stripped_cmd:
                candidates.append((cid, "strip-cmd"))

    # Layer 4 — strip decimal.
    for variant in (normalized, stripped_cmd or ""):
        decimal_stripped = _strip_decimal(variant) if variant else None
        if decimal_stripped:
            for cid in contract_ids:
                if _normalize(cid) == decimal_stripped:
                    candidates.append((cid, "strip-decimal"))

    # Layer 5 — substring: contract step_id appears in normalized label.
    if not candidates:
        for cid in contract_ids:
            cid_norm = _normalize(cid)
            if cid_norm and cid_norm in normalized:
                candidates.append((cid, "substring"))

    # Layer 6 — slug comparison.
    if not candidates:
        label_slug = _label_to_slug(label)
        if label_slug:
            for cid in contract_ids:
                if cid == label_slug:
                    candidates.append((cid, "slug"))

    if not candidates:
        return (f"<unresolved>:{_hash_id(label)}", "unresolved")

    # Tie-break.
    # 1. Prefer kind_hint match if provided.
    # 2. Else prefer kind=step over kind=group.
    # 3. Then prefer smaller Levenshtein distance from label-slug to step_id.
    # 4. If still ambiguous → fail-closed unresolved.
    if len(candidates) == 1:
        return candidates[0]

    # Dedupe (same (id, match_class) pairs may appear from multiple layers).
    seen = set()
    deduped: list[tuple[str, MatchClass]] = []
    for c in candidates:
        if c[0] not in seen:
            seen.add(c[0])
            deduped.append(c)
    if len(deduped) == 1:
        return deduped[0]

    # Apply kind tie-break.
    if kind_hint:
        kind_matches = [c for c in deduped if kind_by_id.get(c[0]) == kind_hint]
        if len(kind_matches) == 1:
            return kind_matches[0]
        if len(kind_matches) > 1:
            deduped = kind_matches

    step_matches = [c for c in deduped if kind_by_id.get(c[0]) == "step"]
    if len(step_matches) == 1:
        return step_matches[0]
    if len(step_matches) > 1:
        deduped = step_matches

    # Levenshtein tie-break.
    label_slug = _label_to_slug(label)
    if label_slug:
        ranked = sorted(deduped, key=lambda c: _levenshtein(label_slug, c[0]))
        if len(ranked) >= 2 and _levenshtein(label_slug, ranked[0][0]) < _levenshtein(label_slug, ranked[1][0]):
            return ranked[0]

    # Still ambiguous → fail-closed.
    return (f"<unresolved>:{_hash_id(label)}", "unresolved")


def status_precedence(*statuses: str) -> str:
    """Pick highest-precedence status when multiple labels resolve to same step_id.

    Precedence: in_progress > completed > pending.
    """
    if not statuses:
        return "pending"
    ranks = {"in_progress": 3, "completed": 2, "pending": 1}
    best = max(statuses, key=lambda s: ranks.get(s, 0))
    return best


def resolve_alias(step_id: str) -> Optional[str]:
    """If step_id is a legacy alias, return current canonical step_id; else None.

    Used by emit-tasklist.py:_write_contract merge to migrate statuses across renames.
    """
    for current, aliases in STEP_ID_ALIASES.items():
        if step_id == current:
            return None
        if step_id in aliases:
            return current
    return None
