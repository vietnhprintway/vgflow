#!/bin/bash
# vg-challenge-answer-wrapper.sh — safe fd-3 capture for answer-challenger (v1.9.5 R3.4+)
#
# Wraps the answer-challenger helper's fd-3 content emission so orchestrators
# don't have to remember exact redirection pattern. A single missed redirect
# causes silent empty-prompt → subagent fails silently → gate skips.
#
# Usage:
#   PROMPT=$(bash .claude/commands/vg/_shared/lib/vg-challenge-answer-wrapper.sh \
#            "$USER_ANSWER" "$ROUND_LABEL" "$COMMAND_NAME" "$ACCUMULATED_DRAFT")
#
# Output (stdout): full prompt CONTENT ready to pass to Task subagent.
# Exit: 0 on success, 1 if helper missing/errored, 2 if answer is trivial (no challenge needed).

set -u

if [ "$#" -lt 3 ]; then
  echo "usage: vg-challenge-answer-wrapper.sh USER_ANSWER ROUND_LABEL COMMAND_NAME [ACCUMULATED_DRAFT]" >&2
  exit 1
fi

USER_ANSWER="$1"
ROUND_LABEL="$2"
COMMAND_NAME="$3"
ACCUMULATED="${4:-}"
: "${PLANNING_DIR:=.vg}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/answer-challenger.sh" 2>/dev/null || {
  echo "⛔ vg-challenge-answer-wrapper: answer-challenger.sh not found at ${SCRIPT_DIR}" >&2
  exit 1
}

if ! type -t challenge_answer >/dev/null 2>&1; then
  echo "⛔ vg-challenge-answer-wrapper: challenge_answer function not exported" >&2
  exit 1
fi

# Trivial-answer auto-skip — preserve helper's v2.6 draft-swap path.
#
# v2.50.5 fix: do not exit before challenge_answer can turn "ok"/"a"/
# "recommended" into the AI draft or chosen option from ACCUMULATED. Only skip
# when the helper can find no substantive draft/option to challenge.
if type -t challenger_is_trivial >/dev/null 2>&1; then
  if challenger_is_trivial "$USER_ANSWER"; then
    CHALLENGE_SUBSTANCE=""
    if type -t challenger_normalize_pick >/dev/null 2>&1; then
      PICK="$(challenger_normalize_pick "$USER_ANSWER")"
      if [ -n "$PICK" ] && [ "$PICK" != "_recommended_" ] \
        && type -t challenger_extract_option >/dev/null 2>&1; then
        CHALLENGE_SUBSTANCE="$(challenger_extract_option "$ACCUMULATED" "$PICK")"
      fi
    fi
    if [ -z "$CHALLENGE_SUBSTANCE" ] \
      && type -t challenger_extract_ai_draft >/dev/null 2>&1; then
      CHALLENGE_SUBSTANCE="$(challenger_extract_ai_draft "$ACCUMULATED")"
    fi
    [ -z "$CHALLENGE_SUBSTANCE" ] && exit 2
  fi
fi

# fd-3 content capture, suppress stdout/stderr noise
challenge_answer "$USER_ANSWER" "$ROUND_LABEL" "$COMMAND_NAME" "$ACCUMULATED" 3>&1 1>/dev/null 2>/dev/null
