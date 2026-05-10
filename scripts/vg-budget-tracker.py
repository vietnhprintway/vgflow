#!/usr/bin/env python3
"""v2.68.0 C6 — Min-budget floor tracker.

Tracks token usage per phase across orchestrator events. Aborts phase
when projected cost exceeds configured floor.

Pricing (USD per 1M tokens, as of 2026-05):
- claude-opus-4-7:        input $15 / output $75
- claude-sonnet-4-6:      input $3  / output $15
- claude-haiku-4-5:       input $1  / output $5
- gpt-5.5 (codex):        input $5  / output $15
- gemini-2.5-pro:         input $2  / output $10

Defaults applied when model unrecognized: input $5 / output $15.
"""
import json
import sys
from pathlib import Path

PRICING_PER_MILLION = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "gpt-5.5": (5.0, 15.0),
    "gpt-5.4": (5.0, 15.0),
    "gemini-2.5-pro": (2.0, 10.0),
    "default": (5.0, 15.0),
}


def _cost(input_tokens: int, output_tokens: int, model: str) -> float:
    in_rate, out_rate = PRICING_PER_MILLION.get(model, PRICING_PER_MILLION["default"])
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


def track(state_file: Path, phase_id: str, *, input_tokens: int, output_tokens: int, model: str) -> dict:
    state = {"phases": {}}
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
    state.setdefault("phases", {}).setdefault(phase_id, {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "events": [],
    })
    phase_data = state["phases"][phase_id]
    phase_data["total_input_tokens"] += input_tokens
    phase_data["total_output_tokens"] += output_tokens
    phase_data["total_cost_usd"] += _cost(input_tokens, output_tokens, model)
    phase_data["events"].append({
        "input_tokens": input_tokens, "output_tokens": output_tokens, "model": model,
    })
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def check_budget(state_file: Path, phase_id: str, floor_usd: float) -> tuple[bool, float]:
    """Return (over_budget, total_cost). over_budget=True triggers abort upstream."""
    if not state_file.exists():
        return False, 0.0
    state = json.loads(state_file.read_text(encoding="utf-8"))
    phase_data = state.get("phases", {}).get(phase_id, {})
    total_cost = phase_data.get("total_cost_usd", 0.0)
    return total_cost > floor_usd, total_cost


def main():
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    track_p = sub.add_parser("track")
    track_p.add_argument("--state-file", required=True, type=Path)
    track_p.add_argument("--phase-id", required=True)
    track_p.add_argument("--input-tokens", type=int, required=True)
    track_p.add_argument("--output-tokens", type=int, required=True)
    track_p.add_argument("--model", required=True)

    check_p = sub.add_parser("check")
    check_p.add_argument("--state-file", required=True, type=Path)
    check_p.add_argument("--phase-id", required=True)
    check_p.add_argument("--floor-usd", type=float, required=True)

    args = p.parse_args()

    if args.cmd == "track":
        track(args.state_file, args.phase_id,
              input_tokens=args.input_tokens, output_tokens=args.output_tokens,
              model=args.model)
        return 0
    elif args.cmd == "check":
        over, cost = check_budget(args.state_file, args.phase_id, args.floor_usd)
        if over:
            print(f"[budget] EXCEEDED: ${cost:.4f} > ${args.floor_usd:.4f}", file=sys.stderr)
            return 1
        print(f"[budget] OK: ${cost:.4f} / ${args.floor_usd:.4f}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
