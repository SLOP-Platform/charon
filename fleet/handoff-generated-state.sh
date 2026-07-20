#!/usr/bin/env bash
# handoff-generated-state.sh — the machine-GENERATED, truth-of-record state block for a session
# handoff. SOURCE this file to get `emit_generated_state`; it is the SAME generator handoff.sh
# uses (single source of truth), factored into a sourceable unit so its RESILIENCE path (GitHub /
# network DOWN at generation time) can be exercised HERMETICALLY by
# fleet/tests/handoff-generated-state.test.sh without running the full handoff.sh (which invokes
# gate.sh + live models).
#
# WHY THIS EXISTS (operator-flagged failure class): handoffs HAND-WRITE state prose ("PR #103 can't
# merge", "PR merged") that can be FALSE — and handoff-check.sh cannot verify arbitrary prose. The
# fix is to GENERATE the verifiable state from LIVE queries so a session physically cannot assert a
# false fact here. The block is the TRUTH-OF-RECORD; the session's prose sits alongside as narrative.
# (Generation-only: the handoff PULLS its state instead of asserting it — there is no separate gate.)
#
# RESILIENCE CONTRACT (do not regress — a GitHub Actions outage blocked us on 2026-07-19):
#   - EVERY live query (gh, git ls-remote) is bounded by a timeout: the generator must never HANG.
#   - On ANY failure (network down, gh missing, non-zero, empty), the line is still EMITTED and
#     marked `UNAVAILABLE (gh/network down at generation)` — never silently omitted, never fabricated.
#   - The whole body runs under `set +e` in a subshell so a stray non-zero cannot abort a caller
#     that runs under `set -euo pipefail` (handoff.sh does).
#
# Sourcing this file has NO side effects (defines a function only) so it is safe to source from a test.

# Repo locations + slugs are env-overridable so the hermetic test can point them at throwaway
# fixture repos (local file:// origins => git ls-remote never touches the network). Defaults fall
# back to handoff.sh's own CHARON_REPO/PRIV_REPO when sourced by it, else the canonical paths.
: "${CHARON_PRODUCT_REPO:=${CHARON_REPO:-/home/stack/code/charon}}"
: "${CHARON_RIG_REPO:=${PRIV_REPO:-/home/stack/charon-private}}"
: "${PROD_SLUG:=SLOP-Platform/charon}"
: "${RIG_SLUG:=Nnyan/charon-private}"
# Bound EVERY live call. Small default; test can shrink it further.
: "${HANDOFF_STATE_TIMEOUT:=15}"

# Machine-parseable UNAVAILABLE marker for the SHA lines (first token after `= ` is the value).
_HS_UNAVAIL='UNAVAILABLE'
_HS_UNAVAIL_NOTE='UNAVAILABLE (gh/network down at generation)'

# origin/master SHA of a repo via `git ls-remote` (network), timeout-bounded, fail-soft.
# Prints a 40-hex SHA on success, or the literal token 'UNAVAILABLE' on any failure.
_hs_origin_master_sha() {
  local repo="$1" sha=""
  [ -d "$repo/.git" ] || [ -e "$repo/.git" ] || { printf '%s' "$_HS_UNAVAIL"; return; }
  sha="$(timeout "$HANDOFF_STATE_TIMEOUT" git -C "$repo" ls-remote origin refs/heads/master 2>/dev/null | awk 'NR==1{print $1}')"
  if printf '%s' "$sha" | grep -qE '^[0-9a-f]{40}$'; then
    printf '%s' "$sha"
  else
    printf '%s' "$_HS_UNAVAIL"
  fi
}

# Open PRs of a gh repo slug, timeout-bounded, fail-soft. Emits `- ...` bullet lines, or a single
# UNAVAILABLE bullet. CI-unverified: PR mergeability/CI is NOT asserted here (only open-state).
_hs_open_prs() {
  local slug="$1" out=""
  command -v gh >/dev/null 2>&1 || { printf -- '- %s\n' "$_HS_UNAVAIL_NOTE"; return; }
  out="$(timeout "$HANDOFF_STATE_TIMEOUT" gh pr list --repo "$slug" --state open \
        --json number,title,isDraft,headRefName \
        -q '.[] | "- #\(.number) \(.title) [draft=\(.isDraft)] head=\(.headRefName) (CI-unverified until checked)"' 2>/dev/null)" || out=""
  if [ -z "$out" ]; then
    # Empty is AMBIGUOUS (truly no open PRs vs. gh failed). Re-probe cheaply: if gh can reach the
    # API at all (a bounded `gh pr list` returning rc 0 with empty output), report "none"; else
    # mark UNAVAILABLE. We distinguish by a second bounded call that just asks for the count.
    if timeout "$HANDOFF_STATE_TIMEOUT" gh pr list --repo "$slug" --state open --json number -q 'length' >/dev/null 2>&1; then
      printf -- '- (no open PRs)\n'
    else
      printf -- '- %s\n' "$_HS_UNAVAIL_NOTE"
    fi
  else
    printf '%s\n' "$out"
  fi
}

# Per-worktree: branches AHEAD of their upstream (stranded-work signal) + uncommitted work.
# Pure-local git (no network) but still timeout-bounded and fail-soft for robustness.
_hs_worktree_state() {
  local repo="$1" label="$2" line wt br up ahead dirty
  [ -d "$repo/.git" ] || [ -e "$repo/.git" ] || { printf -- '- %s: (repo not found)\n' "$label"; return; }
  # `git worktree list --porcelain` => blocks separated by blank lines, `worktree <path>` + `branch <ref>`.
  timeout "$HANDOFF_STATE_TIMEOUT" git -C "$repo" worktree list --porcelain 2>/dev/null \
    | awk '/^worktree /{wt=$2} /^branch /{print wt"\t"$2} /^detached$/{print wt"\tDETACHED"}' \
    | while IFS=$'\t' read -r wt br; do
        [ -n "$wt" ] || continue
        br="${br#refs/heads/}"
        if [ "$br" = "DETACHED" ]; then
          printf -- '- %s %s: DETACHED HEAD\n' "$label" "$wt"
          continue
        fi
        up="$(git -C "$wt" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo '')"
        if [ -n "$up" ]; then
          ahead="$(git -C "$wt" rev-list --count "$up..$br" 2>/dev/null || echo '?')"
        else
          ahead='no-upstream'
        fi
        dirty="$(git -C "$wt" status --porcelain 2>/dev/null | grep -c '.' || true)"
        if [ "${ahead:-0}" != "0" ] || [ "${dirty:-0}" != "0" ]; then
          printf -- '- %s %s [%s]: %s commit(s) ahead of %s, %s file(s) uncommitted\n' \
            "$label" "$wt" "$br" "$ahead" "${up:-<none>}" "$dirty"
        fi
      done
}

# The public entry point: prints the full delimited GENERATED-STATE block to stdout.
emit_generated_state() {
  # Subshell + `set +e` so nothing here can abort a `set -e` caller (handoff.sh). All output is
  # captured from this subshell's stdout.
  (
    set +e
    local gen prod_sha rig_sha
    gen="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    prod_sha="$(_hs_origin_master_sha "$CHARON_PRODUCT_REPO")"
    rig_sha="$(_hs_origin_master_sha "$CHARON_RIG_REPO")"

    printf '<!-- GENERATED-STATE v1 (do not hand-edit) generated=%s -->\n' "$gen"
    printf '### Generated state (truth-of-record — machine-queried, do NOT hand-edit)\n\n'
    printf '> Generated by fleet/handoff.sh from LIVE queries at handoff time. A session physically\n'
    printf '> cannot hand-assert facts here — regenerate to refresh. `UNAVAILABLE` lines mean the\n'
    printf '> query (gh / git remote) was down at generation, NOT that the thing is absent.\n\n'

    printf '**origin/master SHA (git ls-remote, machine-parseable):**\n\n'
    # Machine-parse lines: `origin-master <product|rig> = <sha-or-UNAVAILABLE>`. A reader can diff
    # these against `git ls-remote` themselves; the point is the value here is machine-queried, not
    # a hand-typed claim.
    if [ "$prod_sha" = "$_HS_UNAVAIL" ]; then
      printf 'origin-master product = %s  # %s (%s)\n' "$_HS_UNAVAIL" "$_HS_UNAVAIL_NOTE" "$PROD_SLUG"
    else
      printf 'origin-master product = %s  # %s\n' "$prod_sha" "$PROD_SLUG"
    fi
    if [ "$rig_sha" = "$_HS_UNAVAIL" ]; then
      printf 'origin-master rig = %s  # %s (%s)\n' "$_HS_UNAVAIL" "$_HS_UNAVAIL_NOTE" "$RIG_SLUG"
    else
      printf 'origin-master rig = %s  # %s\n' "$rig_sha" "$RIG_SLUG"
    fi

    printf '\n**Open PRs — product (%s):**\n' "$PROD_SLUG"
    _hs_open_prs "$PROD_SLUG"
    printf '\n**Open PRs — rig (%s):**\n' "$RIG_SLUG"
    _hs_open_prs "$RIG_SLUG"

    printf '\n**Branches ahead of upstream + uncommitted work (stranded-work signal):**\n'
    _hs_worktree_state "$CHARON_PRODUCT_REPO" "product"
    _hs_worktree_state "$CHARON_RIG_REPO" "rig"
    # If NOTHING was stranded/dirty across worktrees, the two calls above print nothing — say so
    # explicitly so an empty region never reads as "the probe failed".
    printf '%s\n' '- (clean if no bullets above)'

    printf '<!-- /GENERATED-STATE -->\n'
  )
}
