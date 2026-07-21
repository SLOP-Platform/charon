#!/usr/bin/env bash
# research.test.sh — FAIL-ON-REVERT self-test for fleet/research.sh (FN4-RESEARCH-GATE).
#
# Runs entirely in a temp registry + temp home for sub-prompts. NEVER touches live
# fleet/state/research-registry or the manager memory store.
#
# Covers (mirrors the ticket's FAIL-ON-REVERT claims):
#   (A) VERIFIER GATE — verifier RED on records that LACK a reuse-check section,
#       contain uncited/prose feature claims, or miss verified cards. Reverting
#       that gate (or its disable-toggle to RESEARCH_VERIFY_DISABLE=1) flips the
#       REJECT -> PASS, proving the gate actually bites.
#       Test shape:
#         a1: uncited-prose record -> REJECT
#         a2: no-reuse-check record -> REJECT
#         a3: no-verified-card record -> REJECT
#         a4: no-verdict-frontmatter record -> REJECT
#         a5: full record with reuse-check + cited cards + verdict -> PASS
#         a6: RESEARCH_VERIFY_DISABLE=1 admits a worst-case record (admit the gate
#             CAN be bypassed by setting that toggle — but ONLY via env override,
#             never silently)
#   (B) PRE-LAUNCH DEDUP/STALENESS GATE — fresh-topic lookup returns the cached
#       record WITHOUT launching a sub-session; stale-topic lookup launches
#       UPDATE mode (writes a sub-session prompt).
#       Test shape:
#         b1: FRESH cached -> prints the record path; no prompt emitted.
#         b2: STALE record -> emits sub-session prompt; prompt includes the
#             UPDATE directive + cites "refresh of <rec>".
#         b3: MISSING (no record) -> emits full-research prompt (default mode).
#         b4: --force on fresh record -> emits full-research prompt (bypass).
#
# Run:  bash fleet/tests/research.test.sh   (exit 0 = all pass)

set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESEARCH="$SRC/research.sh"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }
contains(){ case "$2" in *"$3"*) ok "$1" ;; *) bad "$1 (missing '$3')" ;; esac; }
not_contains(){ case "$2" in *"$3"*) bad "$1 (unexpected '$3')" ;; *) ok "$1" ;; esac; }

[ -x "$RESEARCH" ] || { echo "FATAL: research.sh not found/executable: $RESEARCH" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
REG="$WORK/research-registry"

# Helper: write a small fixture record to <file>.
write_record(){
  local f="$1" reuse="${2:-yes}" cards="${3:-yes}" verdict="${4:-yes}"
  : > "$f"
  printf '%s\n' 'topic: Sample topic' >> "$f"
  printf '%s\n' 'recorded_at: 2026-07-12T00:00:00Z' >> "$f"
  if [ "$verdict" = "yes" ]; then printf '%s\n' 'verdict: ADOPT' >> "$f"; fi
  printf '\n' >> "$f"
  if [ "$reuse" = "yes" ]; then
    printf '%s\n' '## Reuse-Check' >> "$f"
    printf '\n' >> "$f"
    printf '%s\n' 'Searched: fleet/scratch/, fleet/research-registry/.' >> "$f"
    printf '%s\n' 'Nothing relevant — moving on.' >> "$f"
    printf '\n' >> "$f"
  fi
  if [ "$cards" = "yes" ]; then
    printf '%s\n' '## Verified card 1' >> "$f"
    printf '\n' >> "$f"
    printf '%s\n' '- source: https://example.com/docs' >> "$f"
    printf '%s\n' '- evidence: "demonstrates X" — example.com/docs#x' >> "$f"
    printf '%s\n' '- notes: validated 2026-07-12' >> "$f"
    printf '\n' >> "$f"
  fi
}

# ──────────────────────────────────────────────────────────────────────────────
# (A) VERIFIER GATE
# ──────────────────────────────────────────────────────────────────────────────

echo "== (A) VERIFIER GATE =="

# a1 — uncited feature claim must REJECT.
echo "== a1: uncited-prose record rejects =="
GOOD="$WORK/good.md"
REJECT="$WORK/uncited.md"
write_record "$GOOD"
# Sanity: the "good" template must currently pass (otherwise the rest of this test
# is testing a gate that admits by default).
out="$(RESEARCH_REGISTRY_DIR="$REG" "$RESEARCH" --verify "$GOOD" 2>&1)"; rc=$?
check "a0 baseline good record PASSes verifier" "$rc" "0"
contains "a0b verifier stdout says PASS" "$out" "VERIFY: PASS"

{
  printf '%s\n' 'topic: Uncited prose' \
  'recorded_at: 2026-07-12T00:00:00Z' \
  'verdict: ADOPT' \
  '' \
  '## Reuse-Check' \
  '' \
  'No reuse needed.' \
  '' \
  '## Verified card 1' \
  '' \
  'The product can ship a new feature with zero downtime.'
} > "$REJECT"
out="$(RESEARCH_REGISTRY_DIR="$REG" "$RESEARCH" --verify "$REJECT" 2>&1)"; rc=$?
[ "$rc" != "0" ] && ok "a1 uncited-prose record REJECTed" || bad "a1 uncited-prose record REJECTed (got pass rc=$rc)"
contains "a1b verifier stdout says REJECT" "$out" "VERIFY: REJECT"
contains "a1c verifier flags uncited claim" "$out" "uncited feature claim"

# a2 — missing Reuse-Check section must REJECT.
echo "== a2: no-reuse-check record rejects =="
NO_REUSE="$WORK/noreuse.md"
{
  printf '%s\n' 'topic: No reuse' \
  'recorded_at: 2026-07-12T00:00:00Z' \
  'verdict: ADOPT' \
  '' \
  '## Verified card 1' \
  '' \
  '- source: https://example.com/x' \
  '- evidence: "supports Y"'
} > "$NO_REUSE"
out="$(RESEARCH_REGISTRY_DIR="$REG" "$RESEARCH" --verify "$NO_REUSE" 2>&1)"; rc=$?
[ "$rc" != "0" ] && ok "a2 missing-reuse-check REJECTed" || bad "a2 missing-reuse-check REJECTed (got pass rc=$rc)"

# a3 — missing verified card must REJECT.
echo "== a3: no-verified-card record rejects =="
NO_CARD="$WORK/nocard.md"
{
  printf '%s\n' 'topic: No card' \
  'recorded_at: 2026-07-12T00:00:00Z' \
  'verdict: ADOPT' \
  '' \
  '## Reuse-Check' \
  '' \
  'No reuse needed.' \
  '' \
  '## Notes' \
  '' \
  'Just some prose without a Verified card.' \
  'https://example.com/anchor-citation'
} > "$NO_CARD"
out="$(RESEARCH_REGISTRY_DIR="$REG" "$RESEARCH" --verify "$NO_CARD" 2>&1)"; rc=$?
[ "$rc" != "0" ] && ok "a3 no-verified-card REJECTed" || bad "a3 no-verified-card REJECTed (got pass rc=$rc)"

# a4 — missing verdict frontmatter must REJECT.
echo "== a4: no-verdict-frontmatter record rejects =="
NO_VERDICT="$WORK/nov.md"
{
  printf '%s\n' 'topic: No verdict' \
  'recorded_at: 2026-07-12T00:00:00Z' \
  '' \
  '## Reuse-Check' \
  '' \
  'No reuse needed.' \
  '' \
  '## Verified card 1' \
  '' \
  '- source: https://example.com/y' \
  '- evidence: "supports Z"'
} > "$NO_VERDICT"
out="$(RESEARCH_REGISTRY_DIR="$REG" "$RESEARCH" --verify "$NO_VERDICT" 2>&1)"; rc=$?
[ "$rc" != "0" ] && ok "a4 no-verdict REJECTed" || bad "a4 no-verdict REJECTed (got pass rc=$rc)"

# a5 — full valid record PASSes.
echo "== a5: full record PASSes =="
rc=0
out="$(RESEARCH_REGISTRY_DIR="$REG" "$RESEARCH" --verify "$GOOD" 2>&1)" || rc=$?
check "a5 full record verifies" "$rc" "0"

# a5b — --record admits a valid record to the registry (write to REG/, print slot path).
echo "== a5b: --record admits to registry =="
ADMITTED="$WORK/admit.md"
write_record "$ADMITTED"
SLOT_OUT="$(RESEARCH_REGISTRY_DIR="$REG" "$RESEARCH" --record "$ADMITTED" 2>&1)"
rc=$?
check "a5b --record exit 0" "$rc" "0"
contains "a5b --record stdout lists registry slot" "$SLOT_OUT" "$REG/admit.md"

# a6 — RESEARCH_VERIFY_DISABLE=1 makes the worst-case record admit (proves the
# verifier, when DISABLED, does NOT silently catch things; the operator can always
# bypass by setting that flag).
echo "== a6: RESEARCH_VERIFY_DISABLE=1 admits a fabricated record =="
BAD="$WORK/fab.md"
{
  printf '%s\n' 'topic: Fabricated' \
  'recorded_at: 2026-07-12T00:00:00Z' \
  'verdict: ADOPT' \
  '' \
  '(no reuse-check, no verified cards, no citations)'
} > "$BAD"
out="$(RESEARCH_REGISTRY_DIR="$REG" RESEARCH_VERIFY_DISABLE=1 "$RESEARCH" --verify "$BAD" 2>&1)"; rc=$?
check "a6 disable-toggle admits worst-case record" "$rc" "0"
contains "a6b verifier announces it is DISABLED" "$out" "DISABLED"

# ──────────────────────────────────────────────────────────────────────────────
# (B) PRE-LAUNCH DEDUP/STALENESS GATE
# ──────────────────────────────────────────────────────────────────────────────

echo "== (B) PRE-LAUNCH GATE =="

# Manually seed a fresh record (recorded_at = today) and a stale record (year 2000).
FRESH_SLUG="fresh-test-topic"
STALE_SLUG="stale-test-topic"
mkdir -p "$REG"
# Fresh: today's ISO date so weight ≈ 1.0 (well above 0.5).
TODAY="$(date -u +%FT%TZ)"
{
  printf '%s\n' 'topic: Fresh Test Topic' \
    "recorded_at: $TODAY" \
    'verdict: ADOPT' \
    '' \
    '## Reuse-Check' \
    '' \
    'No reuse needed.' \
    '' \
    '## Verified card 1' \
    '' \
    '- source: https://example.com/fresh'
} > "$REG/$FRESH_SLUG.md"
# Stale: 2020 so weight is essentially 0.
{
  printf '%s\n' 'topic: Stale Test Topic' \
    'recorded_at: 2020-01-01T00:00:00Z' \
    'verdict: ADOPT' \
    '' \
    '## Reuse-Check' \
    '' \
    'No reuse needed.' \
    '' \
    '## Verified card 1' \
    '' \
    '- source: https://example.com/stale'
} > "$REG/$STALE_SLUG.md"

# b1 — fresh-topic lookup returns the registry record path; does NOT spawn a prompt.
echo "== b1: FRESH lookup returns cached record =="
RES="$(RESEARCH_REGISTRY_DIR="$REG" RESEARCH_PROMPT_OUT="$WORK/b1.prompt" \
       "$RESEARCH" "Fresh Test Topic" 2>&1)"; rc=$?
check "b1 fresh lookup exit 0" "$rc" "0"
contains "b1b stdout returns the registry record path" "$RES" "$REG/$FRESH_SLUG.md"
not_contains "b1c fresh lookup did NOT spawn a prompt" \
  "$(ls -1 "$WORK" | grep '^b1\.prompt' 2>/dev/null || true)" "b1.prompt"
# Also: stdout should NOT contain a path that has not been written.
not_contains "b1d fresh lookup did NOT silently emit prompt content" "$RES" "METHODOLOGY — must appear in your final record"

# b2 — stale-topic lookup emits a prompt (UPDATE mode).
echo "== b2: STALE lookup emits UPDATE prompt =="
out="$(RESEARCH_REGISTRY_DIR="$REG" RESEARCH_PROMPT_OUT="$WORK/b2.prompt" \
       "$RESEARCH" "Stale Test Topic" 2>&1; echo "RC=$?")"
echo "$out" | grep -q "RC=10" && ok "b2 stale lookup exits 10 (sub-session launch signal)" \
                              || bad "b2 stale lookup exits 10"
[ -s "$WORK/b2.prompt" ] && ok "b2b stale lookup wrote a prompt file" \
                          || bad "b2b stale lookup wrote a prompt file"
grep -q 'UPDATE Stale Test Topic' "$WORK/b2.prompt" && ok "b2c prompt starts with UPDATE directive" \
                                                    || bad "b2c prompt starts with UPDATE directive"
grep -q "refresh of $REG/$STALE_SLUG.md" "$WORK/b2.prompt" && ok "b2d prompt cites prior record path" \
                                                        || bad "b2d prompt cites prior record path"

# b3 — missing-topic lookup emits a FULL-research prompt.
echo "== b3: MISSING lookup emits full-research prompt =="
out="$(RESEARCH_REGISTRY_DIR="$REG" RESEARCH_PROMPT_OUT="$WORK/b3.prompt" \
       "$RESEARCH" "New Unseen Topic" 2>&1; echo "RC=$?")"
echo "$out" | grep -q "RC=10" && ok "b3 missing lookup exits 10" || bad "b3 missing lookup exits 10"
grep -q '^# Research sub-session prompt' "$WORK/b3.prompt" && ok "b3b prompt has standard header" \
                                                          || bad "b3b prompt has standard header"
# Full-research prompt should NOT carry UPDATE directive.
not_contains "b3c missing prompt does NOT say UPDATE" "$(head -1 "$WORK/b3.prompt")" "UPDATE "

# b4 — --force on a fresh record emits a full-research prompt (cache bypass).
echo "== b4: --force bypasses cache =="
out="$(RESEARCH_REGISTRY_DIR="$REG" RESEARCH_PROMPT_OUT="$WORK/b4.prompt" \
       "$RESEARCH" --force "Fresh Test Topic" 2>&1; echo "RC=$?")"
echo "$out" | grep -q "RC=10" && ok "b4 --force launches sub-session even for fresh" \
                                || bad "b4 --force launches sub-session even for fresh"
grep -q '^# Research sub-session prompt' "$WORK/b4.prompt" && ok "b4b --force prompt has standard header" \
                                                          || bad "b4b --force prompt has standard header"

# ──────────────────────────────────────────────────────────────────────────────
# (C) --list renders the registry
# ──────────────────────────────────────────────────────────────────────────────

echo "== (C) --list =="
out="$(RESEARCH_REGISTRY_DIR="$REG" "$RESEARCH" --list 2>&1)"; rc=$?
check "c1 --list exit 0" "$rc" "0"
contains "c2 --list shows fresh slug" "$out" "$FRESH_SLUG"
contains "c3 --list shows stale slug" "$out" "$STALE_SLUG"

# ──────────────────────────────────────────────────────────────────────────────
# (D) MIN-SOURCE-COUNT FLAG (operator add-on)
# ──────────────────────────────────────────────────────────────────────────────

echo "== (D) RESEARCH_MIN_SOURCES flag =="
MIN_REC="$WORK/min.md"
{
  printf '%s\n' 'topic: min-test' \
    'recorded_at: 2026-07-12T00:00:00Z' \
    'verdict: ADOPT' \
    '' \
    '## Reuse-Check' \
    '' \
    'No reuse needed.' \
    '' \
    '## Verified card 1' \
    '' \
    '- source: https://example.com/one'
} > "$MIN_REC"
# Default MIN_SOURCES=1 — record has one URL → should PASS.
out="$(RESEARCH_REGISTRY_DIR="$REG" "$RESEARCH" --verify "$MIN_REC" 2>&1)"; rc=$?
check "d1 default MIN_SOURCES=1 PASSes one-URL record" "$rc" "0"
# Override to 3 — record has one URL → should REJECT.
out="$(RESEARCH_REGISTRY_DIR="$REG" RESEARCH_MIN_SOURCES=3 "$RESEARCH" --verify "$MIN_REC" 2>&1)"; rc=$?
[ "$rc" != "0" ] && ok "d2 MIN_SOURCES=3 REJECTS one-URL record" \
                  || bad "d2 MIN_SOURCES=3 REJECTS one-URL record (got pass)"
not_contains "d3 disable MIN_SOURCES=0 admits one-URL" \
  "$(out_d3=$(RESEARCH_REGISTRY_DIR="$REG" RESEARCH_MIN_SOURCES=0 "$RESEARCH" --verify "$MIN_REC" 2>&1); echo $out_d3; \
     ( [ $? -eq 0 ] && echo disabled_pass || echo disabled_fail ))" \
  "disabled_fail" 2>/dev/null || true
# direct simpler check
out="$(RESEARCH_REGISTRY_DIR="$REG" RESEARCH_MIN_SOURCES=0 "$RESEARCH" --verify "$MIN_REC" 2>&1)"; rc=$?
check "d3 MIN_SOURCES=0 PASSes one-URL record" "$rc" "0"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL FN4-RESEARCH-GATE TESTS PASS"
