#!/usr/bin/env bash
# no-anthropic-in-sg.sh — GUARD: SG/gateway work must NEVER route to an Anthropic/Claude model.
# Claude/Anthropic is the MANAGER's model only; the droid/SG work step is off-Claude by design.
# FAILS (exit 1) if any Anthropic id appears in a tier-models.tsv failover chain — the routing SG
# actually consumes (fleet-droid.sh parses it). This is the un-sneakable enforcement of the rule
# that "keeps sneaking back in" (memory: sg-never-anthropic). Wire into validate_board.sh / the gate.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TSV="${CHARON_TIER_MODELS:-$FLEET/tier-models.tsv}"
PAT='claude|opus|sonnet|haiku|fable|anthropic'

[ -f "$TSV" ] || { echo "no-anthropic-in-sg: tier-models.tsv not found: $TSV" >&2; exit 2; }

# Data rows only (tier<TAB>chain); skip comments/blank.
hits="$(grep -vE '^[[:space:]]*(#|$)' "$TSV" | grep -iE "$PAT" || true)"
if [ -n "$hits" ]; then
  echo "no-anthropic-in-sg: FAIL — Anthropic/Claude id in a tier chain (SG must NEVER route to Anthropic):" >&2
  printf '%s\n' "$hits" >&2
  echo "Remove it — Claude is the manager's model only. See memory sg-never-anthropic." >&2
  exit 1
fi
echo "no-anthropic-in-sg: OK — no Anthropic id in any SG tier chain"
