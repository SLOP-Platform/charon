#!/usr/bin/env bash
# lib/dogfood-attribution.sh — shared failure-attribution classifier for
# dogfood-eval.sh. Sourced, never executed directly (same convention as
# lib/sections.sh) so both the harness AND selftest/test_dogfood_attribution.sh
# can call the exact same logic against real vs. synthetic charon-run.sh logs
# — no re-derivation, no drift.
#
# BUG THIS FILE FIXES (found 2026-07-13 auditing the Path C ranking): the old
# inline classifier in dogfood-eval.sh matched "ALL MODELS EXHAUSTED" and
# stamped `provider-throttled` REGARDLESS of the real cause. Since dogfood-eval
# always invokes charon-run.sh with exactly ONE candidate model, that banner
# fires for ANY nonzero exit (charon-run.sh's own "failing over" message always
# runs out of models after the first), so it was catching:
#   - minimax-m2.7 / PROVIDER-URL-HELPER: a LOCAL "database is locked" sqlite
#     error from opencode's own session store (rc=1) — nothing to do with any
#     provider's rate limit.
#   - phi-4, all 4 runs (both tickets, both timestamps): an opaque
#     `{"name":"UnknownError", ...}` from the gateway (rc=1) — confirmed by a
#     direct DeepInfra probe (see PATH-C-RANKING-CORRECTED.md) that DeepInfra
#     is FUNDED and phi-4 answers plain completions fine; the failure is
#     something else entirely (agentic/tool-call format?), not a rate limit.
#   - deepseek-v4-flash / kimi-k2.6 on TOOL-REPAIR-MUTATING: charon-run.sh's
#     own transcript shows the candidate's real fix landed, ALL gate checks
#     printed passing, THEN a single TRAILING post-completion call hit a real
#     provider/session limit and charon-run.sh exited nonzero on that basis
#     alone — even though dogfood-eval's own independent re-grade (gate pass +
#     ticket pytest pass) proves the real work was already done and correct.
#
# A gate-passing, test-passing run must never be labeled a provider failure.

# classify_attribution <rc> <out_log_path>
# Prints exactly one attribution bucket. Order matters: specific local/opaque
# signatures are checked BEFORE the generic "ALL MODELS EXHAUSTED" catch-all,
# since that banner alone is not evidence of a real rate-limit for a
# single-model invocation.
classify_attribution() {
  local rc="$1" out_log="$2"
  if [ "$rc" -eq 0 ]; then
    echo "ran-to-completion"; return
  fi
  if grep -q 'TIMEOUT (rc=124.*CAUSE: gateway pool exhausted' "$out_log" 2>/dev/null; then
    echo "provider-degraded->retry(pool-exhausted-on-timeout)"; return
  fi
  if grep -q 'TIMEOUT (rc=124.*too-slow FAIL' "$out_log" 2>/dev/null; then
    echo "too-slow(latency-budget-exceeded)"; return
  fi
  if grep -q "hit a provider/session LIMIT" "$out_log" 2>/dev/null; then
    echo "provider-throttled->try-another(limit-hit)"; return
  fi
  if grep -qi "database is locked" "$out_log" 2>/dev/null; then
    echo "local-error(db-lock; rc=$rc; not-a-provider-symptom)"; return
  fi
  if grep -q '"name": *"UnknownError"' "$out_log" 2>/dev/null; then
    echo "local-error(opaque-server-error; rc=$rc; needs human triage — not auto-disqualified as model-quality or provider-limit)"; return
  fi
  if grep -q "ALL MODELS EXHAUSTED" "$out_log" 2>/dev/null; then
    echo "provider-throttled->try-another(all-exhausted)"; return
  fi
  if grep -q "exited nonzero" "$out_log" 2>/dev/null; then
    echo "error-nonlimit(rc=$rc; needs human triage, not auto-disqualified as model-quality)"; return
  fi
  echo "unknown"
}

# reclassify_trailing_success <attribution> <rc> <n_changed> <gate_verdict> <test_verdict>
# A provider/session hiccup on a call made AFTER the candidate's real diff
# already passed BOTH objective grades is a trailing artifact of the
# candidate's own session, not evidence the candidate failed — reclassify it
# so the overall verdict logic can still credit the (already-graded) work.
reclassify_trailing_success() {
  local attribution="$1" rc="$2" n_changed="$3" gate_verdict="$4" test_verdict="$5"
  if [ "$rc" -ne 0 ] && [[ "$attribution" == provider-* ]] \
     && [ "${n_changed:-0}" -gt 0 ] && [ "$gate_verdict" = "pass" ] \
     && { [ "$test_verdict" = "pass" ] || [ "$test_verdict" = "not-given" ]; }; then
    echo "ran-to-completion(trailing-provider-call-after-success: was ${attribution})"
    return
  fi
  echo "$attribution"
}
