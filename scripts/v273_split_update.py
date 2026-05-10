"""v2.73.0 T6-T10 — split commands/vg/update.md into _shared/update/*.md sub-files.

Strategy (mirrors v2.72.0 migrate split):
- Each invocation extracts ONE group of consecutive <step name="..."> blocks.
- Reads canonical (commands/vg/update.md), writes:
    * NEW _shared/update/<group>.md with verbatim extracted bytes wrapped in
      <process>...</process> (no surrounding frontmatter — sub-files are content-only).
    * Modified update.md with extracted blocks replaced by a slim routing snippet.
- Mirrors the result byte-identically to .claude/commands/vg/update.md
  and .claude/commands/vg/_shared/update/<group>.md.
- Preserves CRLF line endings everywhere (file is opened in binary mode).

Usage:
    python3 scripts/v273_split_update.py <group>

where <group> is one of: preflight, version-and-changelog, fetch-and-merge,
rotate-and-repair, sync-and-report.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys


GROUPS = {
    "preflight": {
        "title": "### Preflight section (extracted v2.73.0 T6)",
        "shared_rel": "_shared/update/preflight.md",
        "steps": ["0_preflight", "1_check_only_mode"],
        "blurb": "Includes 2 steps: 0_preflight, 1_check_only_mode.",
    },
    "version-and-changelog": {
        "title": "### Version + changelog (extracted v2.73.0 T7)",
        "shared_rel": "_shared/update/version-and-changelog.md",
        "steps": ["2_version_compare", "3_changelog_preview", "4_breaking_gate"],
        "blurb": "Includes 3 steps: 2_version_compare, 3_changelog_preview, 4_breaking_gate.",
    },
    "fetch-and-merge": {
        "title": "### Fetch + merge (extracted v2.73.0 T8)",
        "shared_rel": "_shared/update/fetch-and-merge.md",
        "steps": [
            "5_fetch_tarball",
            "6_three_way_merge_per_file",
            "6b_verify_gate_integrity",
        ],
        "blurb": (
            "Includes 3 steps: 5_fetch_tarball, 6_three_way_merge_per_file, "
            "6b_verify_gate_integrity."
        ),
    },
    "rotate-and-repair": {
        "title": "### Rotate + repair (extracted v2.73.0 T9)",
        "shared_rel": "_shared/update/rotate-and-repair.md",
        "steps": ["7_rotate_ancestor_and_version", "7b_repair_hooks"],
        "blurb": "Includes 2 steps: 7_rotate_ancestor_and_version, 7b_repair_hooks.",
    },
    "sync-and-report": {
        "title": "### Sync + report (extracted v2.73.0 T10 — final)",
        "shared_rel": "_shared/update/sync-and-report.md",
        "steps": [
            "8_sync_codex",
            "8b_repair_playwright_mcp",
            "8c_ensure_graphify",
            "9_report",
        ],
        "blurb": (
            "Includes 4 steps: 8_sync_codex, 8b_repair_playwright_mcp, "
            "8c_ensure_graphify, 9_report."
        ),
    },
}


CANONICAL_UPDATE = Path("commands/vg/update.md")
MIRROR_UPDATE = Path(".claude/commands/vg/update.md")
# Sub-file paths in GROUPS use the form "_shared/update/<name>.md"; we anchor them
# under commands/vg/ (canonical) and .claude/commands/vg/ (mirror).
CANONICAL_VG_DIR = Path("commands/vg")
MIRROR_VG_DIR = Path(".claude/commands/vg")


def find_step_block(data: bytes, step_name: str) -> tuple[int, int]:
    """Return (start, end) byte offsets of `<step name="..."> ... </step>\\r\\n?`.

    The end offset is positioned right after the trailing newline of the closing
    </step> tag so that consecutive blocks can be combined cleanly.
    """
    open_tag = f'<step name="{step_name}">'.encode("ascii")
    close_tag = b"</step>"
    start = data.find(open_tag)
    if start < 0:
        raise SystemExit(f"missing opening tag for step {step_name!r}")
    close_search_from = start + len(open_tag)
    close = data.find(close_tag, close_search_from)
    if close < 0:
        raise SystemExit(f"unclosed step {step_name!r}")
    end = close + len(close_tag)
    # Consume trailing CRLF / LF so the routing snippet sits cleanly afterwards
    if data[end:end + 2] == b"\r\n":
        end += 2
    elif data[end:end + 1] == b"\n":
        end += 1
    return start, end


def split_group(group_key: str) -> tuple[int, int, int]:
    """Extract `group_key` from update.md, write sub-file + slim routing.

    Returns (lines_before, lines_after, sub_file_lines).
    """
    if group_key not in GROUPS:
        raise SystemExit(f"unknown group {group_key!r}; valid: {list(GROUPS)}")
    g = GROUPS[group_key]

    raw = CANONICAL_UPDATE.read_bytes()
    lines_before = raw.count(b"\n")

    # Locate each step block contiguously
    spans: list[tuple[int, int]] = []
    for step in g["steps"]:
        spans.append(find_step_block(raw, step))

    # Steps must be contiguous — assert we won't lose interleaved content
    for (s1, e1), (s2, _e2) in zip(spans, spans[1:]):
        between = raw[e1:s2]
        # Allow only whitespace (CRLF / LF / spaces) between adjacent step blocks
        if between.strip() != b"":
            raise SystemExit(
                f"non-whitespace content between steps {g['steps']} for group "
                f"{group_key!r} — refusing to split blindly. Found: {between!r}"
            )

    block_start = spans[0][0]
    block_end = spans[-1][1]
    extracted = raw[block_start:block_end]

    # Build sub-file content (CRLF-preserved, content-only — no frontmatter)
    sub_header = (
        f"<!-- v2.73.0 T6-T10 extraction — verbatim step blocks from "
        f"commands/vg/update.md -->\r\n"
        f"<!-- Group: {group_key} | Steps: {', '.join(g['steps'])} -->\r\n"
        f"\r\n"
        f"<process>\r\n"
        f"\r\n"
    ).encode("utf-8")
    sub_footer = b"\r\n</process>\r\n"
    sub_body = sub_header + extracted + sub_footer

    # Build slim routing snippet (also CRLF)
    steps_csv = ", ".join(g["steps"])
    routing = (
        f"{g['title']}\r\n"
        f"\r\n"
        f"Read `{g['shared_rel']}` and follow it exactly.\r\n"
        f"{g['blurb']}\r\n"
        f"\r\n"
        f"Step coverage: {steps_csv}.\r\n"
        f"\r\n"
    ).encode("utf-8")

    # Patch update.md: replace [block_start, block_end) with routing
    new_raw = raw[:block_start] + routing + raw[block_end:]
    lines_after = new_raw.count(b"\n")

    # Write canonical sub-file
    canonical_sub = CANONICAL_VG_DIR / Path(g["shared_rel"])
    canonical_sub.parent.mkdir(parents=True, exist_ok=True)
    canonical_sub.write_bytes(sub_body)

    # Write mirror sub-file (byte-identical)
    mirror_sub = MIRROR_VG_DIR / Path(g["shared_rel"])
    mirror_sub.parent.mkdir(parents=True, exist_ok=True)
    mirror_sub.write_bytes(sub_body)

    # Write canonical update.md
    CANONICAL_UPDATE.write_bytes(new_raw)
    # Write mirror update.md (byte-identical)
    MIRROR_UPDATE.write_bytes(new_raw)

    sub_lines = sub_body.count(b"\n")
    return lines_before, lines_after, sub_lines


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 scripts/v273_split_update.py <group>", file=sys.stderr)
        print(f"valid groups: {list(GROUPS)}", file=sys.stderr)
        return 2
    group_key = argv[1]
    before, after, sub = split_group(group_key)
    print(
        f"{group_key}: update.md {before} -> {after} lines | "
        f"sub-file {GROUPS[group_key]['shared_rel']} = {sub} lines"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
