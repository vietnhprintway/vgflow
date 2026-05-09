import re
from pathlib import Path

CANONICAL = Path("commands/vg/_shared/build/close.md")
MIRROR = Path(".claude/commands/vg/_shared/build/close.md")
DEPLOY = Path("commands/vg/deploy.md")
DEPLOY_WHITELIST = {"accepted","tested","reviewed","built-with-debt","built-complete","complete"}


def test_build_writes_status_in_deploy_whitelist():
    """P0-1: build close.md must write a status that deploy accepts.

    Without this, every /vg:deploy after /vg:build hard-blocks with
    'Build not complete' unless --allow-build-incomplete override.
    """
    body = CANONICAL.read_text(encoding="utf-8")
    # Find the steps.build.status assignment in the close.md Python heredoc
    m = re.search(r"'status':\s*'([\w-]+)'\s*,\s*\n\s*'finished_at'", body)
    assert m, "build close.md must set steps.build.status near 'finished_at'"
    status = m.group(1)
    assert status in DEPLOY_WHITELIST, (
        f"build writes status='{status}' but deploy whitelist is {sorted(DEPLOY_WHITELIST)}. "
        f"This means /vg:deploy will hard-block every time without --allow-build-incomplete."
    )


def test_close_md_mirror_byte_identical():
    """VG canonical/mirror invariant: close.md must be byte-identical."""
    if not MIRROR.exists():
        # Some installs only have canonical
        return
    assert CANONICAL.read_bytes() == MIRROR.read_bytes(), (
        "commands/vg/_shared/build/close.md and .claude/commands/vg/_shared/build/close.md "
        "must be byte-identical mirrors"
    )


def test_deploy_whitelist_unchanged():
    """Sanity: ensure deploy.md still has the same whitelist we're aligning to.
    If this test fails, the whitelist drifted and we need to re-evaluate.
    """
    body = DEPLOY.read_text(encoding="utf-8")
    m = re.search(r"accepted\|tested\|reviewed\|built-with-debt\|built-complete\|complete", body)
    assert m, "deploy.md whitelist drifted — verify build status alignment"
