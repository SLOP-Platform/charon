#!/usr/bin/env bash
# THE ONE COMMAND PER TAB.  Usage:  fleet-droid.sh <low|med|high|opus|sonnet|haiku> [--wait <min>] [--retries <n>]
# Loops: claim a ticket for this tier -> run ONE ephemeral claude session on it (worktree, work,
# DRAFT PR base=master, never merges) -> mark submitted -> claim the next. Stands down when no
# tier-eligible work remains.
#
# SELF-FEEDING POOL (--wait): instead of standing down on an empty claim, sleep <min> minutes and
# re-check, up to <n> CONSECUTIVE empty checks (default 6), THEN stand down. Finding work resets
# the counter. An idle tab is just a sleeping shell — no model session burns until it claims. So
# open the pool of tabs ONCE; each rides through dependency gaps (grabbing the next ticket the
# instant a merge unblocks it) and drains to a clean exit when the board is done. No per-ticket
# hand-launching; the manager stays gate-only.
#
# DEFAULT is --wait 3: a bare `fleet-droid.sh <tier>` self-feeds (waits through empty checks)
# rather than quitting on the first empty claim. Pass `--wait 0` for the old one-shot behavior
# (claim once, stand down when empty); raise `--retries` to ride out longer dependency gaps, or `--retries 0` = NEVER stand down (persistent tab: polls every --wait min forever, auto-claiming as work appears).
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── DROID-CLIENT-PREFLIGHT (2026-07-24) ──────────────────────────────────────
# Same fault class charon-run.sh fixes, one layer up. `~/.local/bin` is added to
# PATH ONLY by ~/.bashrc / ~/.profile (interactive or login shells). A tab
# launched via setsid/nohup/`sh -c`/a tool-invoked wrapper gets neither — and
# BOTH `opencode` (the work client) AND `gh` (how this launcher publishes the
# PR) live in ~/.local/bin. So the whole droid loop silently loses two binaries
# based on nothing but how the tab was started.
# APPEND, never prepend: an already-resolvable binary (test stub, deliberate
# operator override) must keep winning; this only adds a fallback location.
case ":${PATH}:" in
  *":$HOME/.local/bin:"*) : ;;
  *) [ -d "$HOME/.local/bin" ] && export PATH="$PATH:$HOME/.local/bin" ;;
esac
# Fail LOUD and EARLY on a missing prereq rather than letting it surface later
# disguised as ticket/model/provider failure. Checked here: the binaries this
# launcher itself shells out to. The work CLIENT is preflighted by
# charon-run.sh (exit 4) — it owns that check because $CHARON_AGENT_CMD is
# swappable and this layer must not assume which client is in play.
_missing=()
for _b in git gh python3 timeout curl; do
  command -v "$_b" >/dev/null 2>&1 || _missing+=("$_b")
done
if [ "${#_missing[@]}" -gt 0 ]; then
  {
    echo "[fleet-droid] FATAL: required binary not found: ${_missing[*]}"
    echo "[fleet-droid]   PATH searched: $PATH"
    echo "[fleet-droid]   LOCAL ENVIRONMENT fault — no ticket claimed, nothing attempted."
    echo "[fleet-droid]   Likely cause: launched from a non-login, non-interactive shell"
    echo "[fleet-droid]   (setsid/nohup/sh -c) that sourced neither ~/.bashrc nor ~/.profile."
  } >&2
  exit 4
fi
unset _b _missing

# derive_gateway_token — re-derive the gateway bearer token from the opencode config and
# EXPORT it, overwriting whatever the shell had.
#
# UNCONDITIONAL OVERWRITE, not a fallback. capability/availability.py PREFERS
# CHARON_GATEWAY_TOKEN from the ambient env, and env-registry.sh's own header documents that
# variable as STALE ("always re-derive from the live opencode config"). Dogfooded: no token
# -> /charon/status answers 302 with a 0-byte body; a STALE token -> the SAME 302/0-byte; the
# correctly derived token -> 200 with parseable JSON. So a `${CHARON_GATEWAY_TOKEN:-derived}`
# shape would be a no-op that leaves the outage fully intact.
#
# env-registry.sh:bearer_token() is the ONE canonical reader (~/.config/opencode/opencode.json
# -> provider.charon.options.apiKey). Sourced through its source guard inside a command
# substitution, so neither its `set -uo pipefail` nor its FLEET/OUTPUT/GATEWAY_URL variables
# leak in here, and its live probe never fires. This is why no second JSON parse is written.
#
# Defined this early so BOTH entry paths get it: the `resolve` dev/test hook (which consults
# the gateway through availability.py) and the main pre-claim preflight. Idempotent.
# The two results are published as GLOBALS (_derived_tok / _env_tok), deliberately not locals: the
# pre-claim gateway preflight further down reports WHICH token it used and whether one could be
# derived at all, and with `set -u` in force a local would make that reporting line die with
# "_derived_tok: unbound variable" (rc 1) instead of the loud, distinct exit 5 — turning the whole
# stand-down into the opaque crash this preflight exists to replace. Both names are `unset` right
# after the preflight so nothing downstream reads a stale token out of the environment.
derive_gateway_token(){
  _derived_tok="" _env_tok="${CHARON_GATEWAY_TOKEN:-}"
  if [ -r "$FLEET/env-registry.sh" ]; then
    _derived_tok="$( . "$FLEET/env-registry.sh" >/dev/null 2>&1 && bearer_token 2>/dev/null || true )"
  fi
  [ -n "$_derived_tok" ] || return 0
  if [ -n "$_env_tok" ] && [ "$_env_tok" != "$_derived_tok" ]; then
    {
      echo "[fleet-droid] WARN: gateway-token-drift — CHARON_GATEWAY_TOKEN from the shell differs from"
      echo "[fleet-droid]   the token in ${CHARON_OPENCODE_CONFIG:-$HOME/.config/opencode/opencode.json}"
      echo "[fleet-droid]   (provider.charon.options.apiKey). opencode.json is AUTHORITATIVE; the shell"
      echo "[fleet-droid]   value is documented stale. PREFERRING THE DERIVED TOKEN for this run."
      echo "[fleet-droid]   Fix your shell profile (or unset CHARON_GATEWAY_TOKEN) to silence this."
    } >&2
  fi
  # Export so EVERY downstream reader picks it up — capability/availability.py, assign.py's
  # --gateway-availability probe, and any child that reads the ambient env — without each of
  # them needing to learn how to derive it.
  export CHARON_GATEWAY_TOKEN="$_derived_tok"
}
CHARON="/home/stack/code/charon"   # DEFAULT product repo (a ticket's `repo:` field overrides per-ticket)
# OFF-CLAUDE WORK CLIENT (SWAPPABLE). The droid's actual work runs THROUGH THE CHARON GATEWAY, not
# `claude -p` (which speaks to Anthropic directly and burns Claude tokens). Default client =
# charon-run.sh (opencode CLI -> `charon/<model>` -> gateway, cross-model failover, "zero Claude
# limit"). The opencode CLI is only the DEFAULT client — it is NOT hardwired: swap the client next
# week by setting CHARON_AGENT_CMD to any executable with the SAME positional contract
#   <cwd> <outlog> <brief-file> <model1> [model2 ...]      (exit 0 = success)
# — one env var, zero other edits. The MANAGER stays on Claude; only this droid work step is off-Claude.
CHARON_AGENT_CMD="${CHARON_AGENT_CMD:-$FLEET/charon-run.sh}"
# WORKTREE-LEAK GUARD (#1): launcher pre-creates the worktree + post-session leak detector.
source "$FLEET/leak-guard.sh"
# P0 #4 (DROID-LIFECYCLE-REAP): the upstream `leak_worktree_setup` (in leak-guard.sh) does
# `git worktree add -B <branch> <base_ref>` which SILENTLY DISCARDS a pre-existing branch
# with unmerged commits (reflog: "Created from <base>" = a full reset). Observed twice
# on FLEET-DEMAND-DRIVEN-ROUTING, recovered by SHA both times. The P0 guard wraps the
# upstream with a "REUSE-IF-UNIQUE-COMMITS" decision: if the ticket branch already exists
# and has commits not in <base_ref>, REUSE it (check the surviving branch out into a fresh
# worktree dir) rather than `-B`-resetting it. Recreate-from-base is only allowed when
# the branch has NO unique commits — i.e. a re-claim of a never-touched branch is
# identical to a fresh create. Same return contract as leak_worktree_setup: 0=ok, 1=fatal,
# 2=refused (needs-push marker present).
p0_worktree_setup(){
  local charon="$1" wt="$2" branch="$3" npmarker="${4:-}" base_ref="${5:-origin/master}"
  if [ -n "$npmarker" ] && [ -e "$npmarker" ]; then
    echo "p0-worktree-setup: REFUSING to (re)create $wt — $npmarker exists (committed-but-unlanded work); land it first." >&2
    return 2
  fi
  git -C "$charon" fetch origin --quiet 2>/dev/null || true
  # Always prune stale worktree admin metadata BEFORE the branch-state check. A leftover
  # `rm -rf`'d worktree dir from a dead droid would otherwise make `git worktree add`
  # fail with "missing but already registered worktree" — exactly the data-loss escape
  # hatch (we'd then `-f` or fall back to the `branch -D` recreate).
  git -C "$charon" worktree prune 2>/dev/null || true
  # FAIL CLOSED (fix #1). This previously read
  #   [ -n "$(git -C "$charon" log --oneline "$base_ref..$branch" 2>/dev/null)" ]
  # where an EMPTY string meant "no unique commits" — but `git log` also prints nothing when it
  # FAILS, e.g. when $base_ref does not resolve. That collapsed "this branch is empty" and "I
  # could not tell" into the same answer, and the answer routed to the RECREATE-FROM-BASE path
  # below (`leak_worktree_setup`), which deletes the branch and resets it to base. Reuse
  # `_lg_unlanded_count` from leak-guard.sh (fix #5) — it verifies the base resolves FIRST and
  # signals UNRESOLVABLE + rc 1 rather than 0. Unknown is treated as HAS WORK: preserve.
  local has_unique=0 branch_exists=0 uniq_n uniq_rc=0
  if git -C "$charon" show-ref --verify --quiet "refs/heads/$branch"; then branch_exists=1; fi
  if [ "$branch_exists" -eq 1 ]; then
    uniq_n="$(_lg_unlanded_count "$charon" "$branch" "$base_ref")" || uniq_rc=$?
    case "$uniq_n" in ''|*[!0-9]*) uniq_rc=1 ;; esac
    if [ "$uniq_rc" -ne 0 ]; then
      # UNKNOWN — must never read as "safe to reset". Preserve the branch as if it had work.
      echo "p0-worktree-setup: base ref '$base_ref' is UNRESOLVABLE in $charon — FAILING CLOSED, treating $branch as if it holds unmerged work (will REUSE, never recreate)." >&2
      has_unique=1
    elif [ "$uniq_n" -gt 0 ]; then
      has_unique=1
    fi
  fi
  if [ "$has_unique" -eq 1 ]; then
    # PRESERVE: branch has unmerged commits. Reuse the worktree if it's still attached;
    # otherwise check the surviving branch out into the worktree dir. Never `-B`, never
    # `branch -D`, never `--force` — that is the data-loss path.
    if [ -d "$wt" ] && [ -n "$(git -C "$charon" worktree list --porcelain 2>/dev/null | grep -F "branch refs/heads/$branch")" ]; then
      echo "p0-worktree-setup: REUSING $wt (branch $branch has unmerged commits; P0 #4 guard)." >&2
      return 0
    fi
    mkdir -p "$(dirname "$wt")"
    if git -C "$charon" worktree add "$wt" "$branch" >/dev/null; then
      echo "p0-worktree-setup: REUSED surviving branch $branch into $wt (had unmerged commits; P0 #4 guard)." >&2
      return 0
    fi
    echo "p0-worktree-setup: FATAL — could not reuse surviving branch $branch in $wt; refusing to fall back to a -B reset." >&2
    return 1
  fi
  # NO unique commits: safe to recreate from base. Hand off to the upstream's proven path.
  leak_worktree_setup "$charon" "$wt" "$branch" "" "$base_ref"
}
# MULTI-REPO: maps a ticket's `repo:` field -> repo path / worktree / base branch / gate.
# Absent field -> key `charon` (product) => IDENTICAL behavior to the old hardwired path.
source "$FLEET/repo-registry.sh"
usage(){ echo "usage: fleet-droid.sh <frontier|strong|economy|low|med|high|opus|sonnet|haiku> [--wait <min>] [--retries <n>] [--patience <cycles>] [--serial-justified=<reason>] [--only <TICKET-ID>] [--push|--push-only] [--tick <sec>]"; exit 2; }

# ---- DETENTION-REDLINE: shared tier/chain helpers ------------------------------------------------
# Defined ONCE and used by BOTH the main claim loop and the `resolve` hook below, so the chain a
# test observes is produced by the EXACT code that runs in production (production path == test path).
# normalize legacy/alias tier args (high/opus, med/sonnet, low/haiku) -> canonical frontier/strong/economy
canon_tier(){ case "$1" in
  high|opus)   echo frontier;;
  med|sonnet)  echo strong;;
  low|haiku)   echo economy;;
  *)           echo "$1";;
esac; }
# canonical tier -> comma failover chain from the tier-models data file. $NF (last field) not $2 —
# tolerant of accidental extra tabs / column alignment.
tier_chain(){ local canon="$1" tmf="${CHARON_TIER_MODELS:-$FLEET/tier-models.tsv}"
  awk -F'\t' -v t="$canon" '$1!~/^#/ && $1==t {print $NF; exit}' "$tmf" 2>/dev/null || true; }
# Given a work_class and a tier's model chain, print the SURVIVING chain (comma-separated) after
# dropping HARD-detained models for that work_class; advisory-flagged models STAY (with a loud
# warning). Returns 7 if the WHOLE chain is HARD-detained (caller must FAIL LOUD — never run a
# detained model). model-detention.sh reads the grader-owned scorecard READ-ONLY.
detention_filter_chain(){
  local wc="$1"; shift
  local kept=() m drc
  for m in "$@"; do
    set +e; bash "$FLEET/model-detention.sh" check "$m" "$wc"; drc=$?; set -e
    case "$drc" in
      3) echo "[detention] HARD-detained: $m for work_class '$wc' — EXCLUDED from chain (scorecard redline: fabrication)." >&2 ;;
      1) echo "[detention] ADVISORY: $m flagged (>=50% block rate) for work_class '$wc' — KEPT in chain, watch closely." >&2; kept+=("$m") ;;
      *) kept+=("$m") ;;
    esac
  done
  [ "${#kept[@]}" -gt 0 ] || return 7
  ( IFS=','; echo "${kept[*]}" )
}

# ---- CRIPPLE #2/#3 (FLEET-DEMAND-DRIVEN-ROUTING): capped-filter + cost-band spill-up -------------
# tier_canon_path: the cost-band SSOT doc. CHARON_TIER_CANON is a FILE seam (same shape as
# CHARON_TIER_MODELS / CHARON_SCORECARD_TSV / CHARON_GATEWAY_STATUS_FILE) so tests can point the
# parsers at a fixture SSOT. Deliberately a FILE path and never a cap VALUE: no env var can hand
# the cost cap a number, so the cap can only ever come from a config file (see spill_ceiling_tier).
tier_canon_path(){ echo "${CHARON_TIER_CANON:-$FLEET/state/TIER-CANON.md}"; }

# cost_tier_axis: the canonical cost-band axis, CHEAPEST-FIRST, space-separated, PARSED from
# TIER-CANON.md's CANONICAL_COST_TIERS (the single source — no hardcoded ladder in code), with a
# fail-safe literal fallback matching that doc so the dispatcher can never die because the doc moved.
cost_tier_axis(){
  local axis=""
  axis="$(awk -F'=' '/CANONICAL_COST_TIERS[[:space:]]*=/{gsub(/[^a-z, ]/,"",$2); gsub(/[ ,]+/," ",$2); sub(/^ +/,"",$2); print $2; exit}' "$(tier_canon_path)" 2>/dev/null || true)"
  [ -n "$axis" ] || axis="economy strong frontier"   # fail-safe: matches TIER-CANON.md's axis
  echo "$axis"
}

# next_tier_up: given a canonical cost-band tier, echo the NEXT more-expensive band on the axis
# (economy -> strong -> frontier). Echoes EMPTY when already at the top band or when off-axis.
next_tier_up(){
  local cur="$1" prev="" t
  for t in $(cost_tier_axis); do
    [ "$prev" = "$cur" ] && { echo "$t"; return 0; }
    prev="$t"
  done
  echo ""   # cur is the top band (frontier) or off-axis — no higher tier
}

# tier_rank <tier> -> 0-based position on the cheapest-first axis; EMPTY + rc 1 when off-axis.
tier_rank(){
  local want="$1" i=0 t
  for t in $(cost_tier_axis); do
    [ "$t" = "$want" ] && { echo "$i"; return 0; }
    i=$((i+1))
  done
  echo ""; return 1
}

# tier_above <a> <b> -> rc 0 when band <a> is MORE EXPENSIVE than band <b>. FAIL CLOSED: if either
# band is off-axis (unrankable) the answer is "yes, above" — an unrecognisable band is never
# treated as cheap enough to escalate into.
tier_above(){
  local ra rb
  ra="$(tier_rank "$1")" || return 0
  rb="$(tier_rank "$2")" || return 0
  { [ -n "$ra" ] && [ -n "$rb" ]; } || return 0
  [ "$ra" -gt "$rb" ]
}

# ---- COST-CAP GUARDRAIL (MONEY PATH) ------------------------------------------------------------
# spill_ceiling_tier: the MOST EXPENSIVE cost band a COST-driven spill-up may escalate INTO, read
# from `SPILL_UP_COST_CEILING` in the cost-band SSOT (fleet/state/TIER-CANON.md — the same doc that
# already owns the axis and the $/Mtok thresholds; the cap is a routing-cost policy, so it lives
# with the cost-band definition rather than in a new parallel config).
#
# FAIL CLOSED, by construction: this echoes EMPTY whenever the key is missing, empty, malformed, or
# names a band that is not on the axis — and the caller treats EMPTY as "no cost-driven spill-up at
# all" (ceiling := the ticket's own starting band). An absent/blank/garbage value therefore means
# ZERO escalation, never "no cap". There is deliberately NO in-code default ceiling: a hardcoded
# fallback here would be exactly the "unset config silently means unlimited" hole this guardrail
# exists to close (and would be a second source of truth the doc could drift from).
#
# Adopt-vs-build: no maintained library models "a bash dispatcher's cost-band escalation ladder"
# (LiteLLM's max_budget/soft-budget caps SPEND at the gateway plane — a different, complementary
# control that cannot refuse an escalation decision made HERE, before any request is issued), so
# the guardrail is a ~20-line policy read over config we already own.
spill_ceiling_tier(){
  local raw=""
  raw="$(awk -F'=' '/^[[:space:]]*SPILL_UP_COST_CEILING[[:space:]]*=/{gsub(/[^a-zA-Z]/,"",$2); print tolower($2); exit}' "$(tier_canon_path)" 2>/dev/null || true)"
  [ -n "$raw" ] || { echo ""; return 0; }
  tier_rank "$raw" >/dev/null 2>&1 || { echo ""; return 0; }   # off-axis value -> fail closed
  echo "$raw"
}

# exhaust_led <model-or-band> <event> <note>: append ONE row to the provider-exhaustion ledger the
# fleet already records routing/exhaustion events in. Same file, same 5-column schema
# (ts/job/model/event/note) and the same CHARON_EXHAUST_LEDGER override that charon-run.sh:17-21
# owns — a cost-cap hit is an exhaustion event, so it belongs in THAT ledger, not a new sink.
# (Not factored into a shared helper: charon-run.sh sources no shared lib, and rewiring the live
# work-executor's ledger writer mid-branch is a bigger money-path blast radius than this 3-liner.)
# Best-effort by design: a ledger write can never fail a dispatch decision.
COST_CAP_LEDGER="${CHARON_EXHAUST_LEDGER:-/home/stack/charon-private/fleet/provider-exhaustion-ledger.tsv}"
exhaust_led(){
  [ -f "$COST_CAP_LEDGER" ] || printf 'ts\tjob\tmodel\tevent\tnote\n' > "$COST_CAP_LEDGER" 2>/dev/null || true
  printf '%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "${CHARON_JOB_REF:-${DROID:-fleet-droid}}" \
    "$1" "$2" "$3" >> "$COST_CAP_LEDGER" 2>/dev/null || true
  return 0
}

# capped_filter_chain: drop gateway-CAPPED models (every provider that can serve the id is
# parked/drained/cooled per /charon/status — CRIPPLE #2's GatewayStatusAvailability) from a chain.
# Prints the surviving comma chain on stdout. Return contract, mirroring availability.py's
# EXIT_ALL_CAPPED / EXIT_STATUS_UNAVAILABLE:
#   0  filtered against a snapshot we actually READ; stdout = survivors.
#   7  every model is POSITIVELY capped (tier exhausted -> caller may SPILL UP).
#   8  the capped-exclusion COULD NOT RUN (gateway unreachable / 401 / no bearer token /
#      unparseable snapshot / python3 or availability.py missing). We know nothing about capped
#      state -> caller must DETAIN, never spill and never treat this as "nothing capped".
#
# FAIL-OPEN DEFECT, FIXED HERE (money path). This used to swallow stderr (`2>/dev/null`) and map
# every non-7 error to "keep all, rc 0" — byte-for-byte identical to a healthy gateway reporting
# nothing capped. A dispatcher running without a gateway token (the live gateway answers 401
# "missing or invalid bearer token" unauthenticated) therefore had the ENTIRE capped-exclusion
# silently no-op: it filtered nothing, spent against parked/drained providers, and surfaced
# nothing. stderr is now PASSED THROUGH (the real error is visible) and an unreadable snapshot is
# its own return code, so "nothing capped" and "could not ask" can never be confused again.
#
# The missing-prerequisite case (no python3 / no availability.py) is the SAME class — the filter
# does not run — so it takes the same rc 8 path rather than a quiet pass-through: a rig that cannot
# evaluate caps must stop loudly, not spend blind.
capped_filter_chain(){
  local py="$FLEET/capability/availability.py"
  if ! { [ -f "$py" ] && command -v python3 >/dev/null 2>&1; }; then
    echo "[fleet-droid] capped-filter PREREQUISITE MISSING (python3 and/or $py) — gateway capped-exclusion cannot run." >&2
    return 8
  fi
  local out rc
  # stderr is NOT redirected: availability.py's diagnostic (and any traceback) must reach the
  # operator/log. Only stdout is captured.
  set +e; out="$(python3 "$py" filter-capped "$@")"; rc=$?; set -e
  [ "$rc" -eq 7 ] && return 7                       # positively ALL-capped -> exhausted
  if [ "$rc" -ne 0 ]; then                          # 8 (unreadable snapshot) or any unexpected rc
    [ "$rc" -eq 8 ] || echo "[fleet-droid] capped-filter exited unexpectedly (rc=$rc) — treating as UNAVAILABLE (see stderr above)." >&2
    return 8
  fi
  local kept=() m
  while IFS= read -r m; do [ -n "$m" ] && kept+=("$m"); done <<<"$out"
  # rc 0 with an empty survivor list breaks the CLI contract (all-capped is rc 7) -> unavailable,
  # NOT a silent keep-all.
  [ "${#kept[@]}" -gt 0 ] || { echo "[fleet-droid] capped-filter returned rc 0 with NO models — contract violation, treating as UNAVAILABLE." >&2; return 8; }
  ( IFS=','; echo "${kept[*]}" )
}

# resolve_runnable_chain: THE single tier -> RUNNABLE-chain resolver used by BOTH the `resolve`
# dev/test hook AND the main claim loop (production path == test path — the whole point of the
# `resolve` hook). For a work_class + STARTING cost-band tier it applies, in order:
#   (1) REORDER  — assign.py real-outcome ranking (gateway-cap-aware pick), advisory
#   (2) DETENTION — drop HARD-detained models (model-detention.sh)
#   (3) CAPPED    — drop gateway-capped models (capped_filter_chain / GatewayStatusAvailability)
# If a tier yields NO runnable model (no chain row, OR whole chain HARD-detained, OR whole chain
# gateway-capped) it SPILLS UP to the next cost band (economy->strong->frontier) and retries —
# operator rule: better a PAID model does the work than it backlogs trying for cheap. Prints the
# runnable comma chain and returns 0; returns 7 when the ladder can go no further. The caller then
# SKIPs + records loop-guard.sh (the per-<droid,ticket> attempt budget) so an unrunnable ticket is
# QUARANTINED after N re-claims rather than re-hammered — the spill-up walks UP the ladder in ONE
# claim instead of re-hammering one band.
#
# (4) COST CAP (money path). Spill-up used to be UNBOUNDED: a run of capped/exhausted cheap legs
# (a free-tier window closing) could walk every ticket into the most expensive band and keep it
# there, with nothing in the loop able to say no. Each hop is now classified by WHY the band was
# unrunnable, and the two reasons are governed differently — deliberately, because they are
# different kinds of escalation:
#   * COST escalation (band was gateway-CAPPED, or has no chain row): bounded by
#     SPILL_UP_COST_CEILING (see spill_ceiling_tier). A hop INTO a band above the ceiling is
#     REFUSED.
#   * SAFETY escalation (band was wholly HARD-detained for this work_class): NOT bounded. Established
#     semantics — tier is a capability FLOOR and money-path detention ESCALATES; a model that
#     fabricated on money-path work must never run, so "cheap" is not an argument for running it.
#     A safety hop that crosses the ceiling is still LOUD + ledgered ('cost-cap-bypass-detention'),
#     so the carve-out is observable rather than a silent hole.
#
# ON A CAP HIT WE **DETAIN**, WE DO NOT ESCALATE AND WE DO NOT HARD-FAIL THE TICKET. The resolver
# returns 7 (the same unrunnable signal the ladder-exhausted case uses), so the claim loop releases
# the ticket back to the board: it stays claimable and is retried on the next claim, i.e. it WAITS
# for a cheaper leg to free (a park to lapse / a free-tier window to reopen). Detain, not fail,
# because the work is valid and the constraint is transient; detain, not escalate, because
# escalation is exactly the overspend this guardrail exists to prevent. It cannot silently overspend
# (the more expensive band is never even offered to the work client — the refusal happens BEFORE any
# model is handed over) and it cannot silently backlog either: every hit prints a greppable
# `COST-CAP:` line, writes a `cost-cap-detain` row to the provider-exhaustion ledger, and burns one
# loop-guard attempt, so a persistently capped ticket is QUARANTINED and surfaced to the operator,
# who is the only one who can authorise spending above the ceiling (by raising it in the SSOT).
resolve_runnable_chain(){
  local wc="$1" start="$2" cur="$2" spilled="" reason=""
  local ceiling; ceiling="$(spill_ceiling_tier)"
  if [ -z "$ceiling" ]; then
    # FAIL CLOSED: absent/blank/malformed cap != "no cap". Cost-driven spill-up is DISABLED
    # (ceiling := the starting band), so a broken SSOT can never authorise an unbounded escalation.
    echo "[fleet-droid] COST-CAP: no usable SPILL_UP_COST_CEILING in $(tier_canon_path) — FAILING CLOSED: cost-driven spill-up DISABLED (cost band '$start' only). Fix the SSOT to re-enable escalation." >&2
    exhaust_led "band:$start" "cost-cap-config-invalid" "work_class=$wc: SPILL_UP_COST_CEILING absent/malformed in $(tier_canon_path) — cost spill-up disabled (fail closed)"
    ceiling="$start"
  fi
  while [ -n "$cur" ]; do
    local static reordered det capf
    static="$(tier_chain "$cur")"
    if [ -z "$static" ]; then
      echo "[fleet-droid] resolve: no gateway model chain for cost band '$cur' — spilling up." >&2
      reason="no-chain"
    else
      reordered="$(assign_reorder_chain "$wc" "$cur" "$static")"
      local -a rmodels=(); IFS=',' read -r -a rmodels <<<"$reordered" || true
      if det="$(detention_filter_chain "$wc" "${rmodels[@]}")"; then
        local -a dmodels=(); IFS=',' read -r -a dmodels <<<"$det" || true
        local caprc=0
        capf="$(capped_filter_chain "${dmodels[@]}")" || caprc=$?
        if [ "$caprc" -eq 0 ]; then
          [ -n "$spilled" ] && echo "[fleet-droid] SPILL-UP: cost band '$start' had NO runnable model (all detained/capped); escalated to '$cur' (cost ceiling '$ceiling') — a paid model does the work rather than backlogging for cheap." >&2
          echo "$capf"; return 0
        elif [ "$caprc" -eq 8 ]; then
          # CAPPED-FILTER UNAVAILABLE -> DETAIN (return 7), the SAME choice the cost cap makes on an
          # invalid ceiling, and for the same reason. We cannot see capped state, so:
          #   * we cannot hand back this band's chain — it may be wholly parked/drained/cooled, and
          #     "keep everything" was precisely the old silent no-op (spend against dead providers);
          #   * we must NOT spill up either — an unreadable snapshot is not evidence of exhaustion,
          #     and escalating on it is a cost-band jump bought with an ERROR (the overspend the
          #     cap exists to refuse). So the ladder stops here; no costlier band is offered.
          # DETAIN, not hard-fail the dispatch: the work is valid and the fault is transient
          # (gateway restart / token not exported). Returning 7 releases the ticket back to the
          # board still claimable, so it retries once the gateway is readable again. It cannot
          # silently overspend (no model is handed to the work client at all) and it cannot
          # silently backlog: the real error is on stderr (no longer swallowed), the greppable
          # `CAPPED-FILTER-UNAVAILABLE:` line prints, a `capped-filter-unavailable` row lands in the
          # provider-exhaustion ledger, and the caller burns one loop-guard attempt so a persistent
          # outage QUARANTINES the ticket and surfaces it to the operator.
          # REMEDIATION TEXT CORRECTED (DROID-CLIENT-PREFLIGHT, 2026-07-24). The old wording blamed
          # "a 401/missing CHARON_GATEWAY_TOKEN" and told the operator to export one. BOTH halves
          # of that were wrong in the way that matters (the old string itself is deliberately not
          # reproduced here — fleet/tests/charon-run-client-preflight.test.sh pins its absence):
          #   - It is a 302, not a 401. The gateway REDIRECTS an unauthenticated /charon/status and
          #     answers with a ZERO-BYTE body, which is why the symptom surfaces as
          #     json.loads("") -> "Expecting value: line 1 column 1 (char 0)" and why any check
          #     comparing against 401 misses it entirely.
          #   - Telling the operator to export one is the ACTION THAT CAUSED THE OUTAGE. A shell that already
          #     exports a STALE CHARON_GATEWAY_TOKEN gets the SAME 302/0-byte answer as a shell with
          #     no token at all (dogfooded both ways), and availability.py PREFERS the env var — so
          #     exporting reproduces the failure instead of fixing it.
          # The only correct remedy is to RE-DERIVE from the opencode config, which the pre-claim
          # preflight at the top of this script now does automatically; reaching this line at all
          # means the gateway went unreadable MID-RUN.
          echo "[fleet-droid] CAPPED-FILTER-UNAVAILABLE: could not read gateway capped state for cost band '$cur' (see the availability error above — typically /charon/status answering 302 with a ZERO-BYTE body because the bearer token is missing OR STALE, or the gateway being down). FAILING CLOSED: gateway capped-exclusion did NOT run, so this band's chain is NOT trusted and is NOT handed over, and NO cost spill-up is taken off an error. DETAINING '$start' work: the ticket is released and stays claimable, retried when gateway status is readable again. FIX: do NOT 'export CHARON_GATEWAY_TOKEN' — a stale value fails identically and availability.py PREFERS the env var. RE-DERIVE it from ${CHARON_OPENCODE_CONFIG:-$HOME/.config/opencode/opencode.json} (provider.charon.options.apiKey), or restore $(printf '%s' "${CHARON_GATEWAY_URL:-http://10.0.1.60:8080}")." >&2
          exhaust_led "band:$cur" "capped-filter-unavailable" "work_class=$wc start=$start ceiling=$ceiling: /charon/status unreadable (auth/reach) — capped-exclusion did not run; DETAINED (fail closed, no spill-up)"
          return 7
        fi
        echo "[fleet-droid] cost band '$cur': ALL models gateway-CAPPED (every provider parked/drained/cooled) — spilling up." >&2
        reason="capped"
      else
        echo "[fleet-droid] cost band '$cur': ALL models HARD-detained for work_class '$wc' — spilling up." >&2
        reason="detained"
      fi
    fi
    local nxt; nxt="$(next_tier_up "$cur")"
    if [ -z "$nxt" ]; then
      echo "[fleet-droid] resolve: cost band '$cur' is the TOP band (frontier) and still has no runnable model — cost-band ladder EXHAUSTED." >&2
      return 7
    fi
    if tier_above "$nxt" "$ceiling"; then
      if [ "$reason" = "detained" ]; then
        # Documented carve-out: safety escalation is not cost-bounded (see header). Loud + ledgered.
        echo "[fleet-droid] COST-CAP: spilling '$cur' -> '$nxt' ABOVE the cost ceiling '$ceiling' because band '$cur' is wholly HARD-detained for work_class '$wc' — safety escalation overrides the cost cap (a detained model must never run). This spends above the ceiling." >&2
        exhaust_led "band:$cur->$nxt" "cost-cap-bypass-detention" "work_class=$wc start=$start ceiling=$ceiling: whole band HARD-detained — safety escalation above the cost ceiling"
      else
        echo "[fleet-droid] COST-CAP: REFUSING to spill '$cur' -> '$nxt' — band '$nxt' is above the configured spill-up cost ceiling '$ceiling' (SPILL_UP_COST_CEILING in $(tier_canon_path)). Reason band '$cur' was unrunnable: $reason. DETAINING '$start' work: the ticket is released and stays claimable so it waits for a cheaper leg to free — it is NOT escalated into a more expensive band and NOT silently dropped. Raise the ceiling in the SSOT to authorise the spend." >&2
        exhaust_led "band:$cur->$nxt" "cost-cap-detain" "work_class=$wc start=$start ceiling=$ceiling reason=$reason: refused cost spill-up above ceiling — DETAINED (retry when a cheaper leg frees)"
        return 7
      fi
    fi
    spilled=1; cur="$nxt"
  done
  return 7
}

# ---- S4 (Gap A rig facet): REAL-OUTCOME ranking consult -----------------------------------------
# Before this, the tier->model resolution above consulted ONLY the static fleet/tier-models.tsv
# chain — capability/assign.py's real-outcome grades (model-scorecard.tsv's source=live lane, see
# capability/grades.py) were computed but never reached this dispatcher. This is the seam: given a
# ticket's work_class + the canonical tier, ask assign.py to RE-RANK the SAME candidate set the
# static chain already offers (--candidates) — it never introduces an unlisted model id the
# gateway chain doesn't already know about. The pick (if any) is promoted to the FRONT of the
# chain; the remainder of the static order follows UNCHANGED as the failover fallback, so a
# real-ranked pick that then fails still rolls through the identical failover chain fleet-droid.sh
# always had. Advisory-only: any failure (no live data yet for this work_class, python3/assign.py
# unavailable, a picked id that isn't even in the candidate set we offered) falls straight back to
# the UNCHANGED static chain — this can never make the dispatcher worse than before it existed.
# CHARON_SCORECARD_TSV (same env-override name model-detention.sh already honors) lets tests point
# both the ranking consult AND the detention filter at one isolated fixture ledger.
assign_reorder_chain(){
  local wc="$1" canon="$2" static_csv="$3" py="$FLEET/capability/assign.py"
  [ -n "$wc" ] && [ -n "$static_csv" ] && [ -f "$py" ] || { echo "$static_csv"; return 0; }
  local tsv_args=()
  [ -n "${CHARON_SCORECARD_TSV:-}" ] && tsv_args=(--tsv "$CHARON_SCORECARD_TSV")
  local picked=""
  # CRIPPLE #2: --gateway-availability makes assign.py consult /charon/status so its real-outcome
  # PICK never promotes a gateway-capped model to the front. This is advisory + fail-open (gateway
  # unreachable -> unknown for all, pick unchanged); the AUTHORITATIVE capped exhaustion signal that
  # triggers spill-up is capped_filter_chain (which also covers ungraded ids assign() never ranks).
  picked="$(python3 "$py" --work-class "$wc" --tier "$canon" --candidates "$static_csv" \
              "${tsv_args[@]}" --gateway-availability --print-model 2>/dev/null)" || true
  # Sanity: never trust a picked id we didn't explicitly offer as a candidate.
  case ",$static_csv," in *",$picked,"*) ;; *) picked="" ;; esac
  if [ -z "$picked" ]; then echo "$static_csv"; return 0; fi
  echo "[fleet-droid] real-outcome ranking (assign.py work_class=$wc tier=$canon): promoting $picked to the front (static chain: $static_csv)." >&2
  local -a static_arr=() rest_arr=()
  IFS=',' read -r -a static_arr <<<"$static_csv"
  local m
  for m in "${static_arr[@]}"; do [ "$m" = "$picked" ] || rest_arr+=("$m"); done
  ( IFS=','; echo "${picked}${rest_arr[*]:+,${rest_arr[*]}}" )
}

# ---- DETENTION-REDLINE: `resolve` dev/test hook --------------------------------------------------
# `fleet-droid.sh resolve <tier> <ticketfile>` resolves a tier + a claimed ticket to its
# POST-DETENTION-FILTER gateway chain using the SAME helpers the claim loop uses (production path ==
# test path). Prints the surviving comma chain on stdout; exits 7 with a loud message when the whole
# chain is HARD-detained for the ticket's work_class — the identical skip decision the loop makes.
if [ "${1:-}" = "resolve" ]; then
  # This hook consults the gateway (capped-exclusion via availability.py), so it needs the
  # SAME derived token the claim loop uses — otherwise `resolve` fails closed with a bogus
  # "all capped" verdict purely because the invoking shell had no/stale token. Same class as
  # the PATH fix above: derive, never inherit.
  derive_gateway_token
  rtier="${2:?resolve needs: <tier> <ticketfile>}"; rtfile="${3:?resolve needs: <tier> <ticketfile>}"
  [ -f "$rtfile" ] || { echo "[fleet-droid] resolve: no such ticket file: $rtfile" >&2; exit 2; }
  rcanon="$(canon_tier "$rtier")"
  rline="$(tier_chain "$rcanon")"
  [ -n "$rline" ] || { echo "[fleet-droid] resolve: no gateway model chain for tier '$rtier' (canonical '$rcanon')." >&2; exit 3; }
  rwc="$(awk -F': ' '$1=="work_class"{sub(/^[^:]*: ?/,"");print;exit}' "$rtfile")"
  if [ -z "$rwc" ]; then
    # F4 (money guardrail, 2026-07-24): this arm used to emit the FULL UNFILTERED CHAIN and
    # exit 0 behind a stderr note. Since detention, gateway capped-exclusion AND the cost cap
    # ALL scope by work_class, a ticket that simply omits the field bypassed every money
    # guardrail at once — and, exiting 0, could never go RED. validate_board.sh mitigates this
    # at BOARD level, but a fail-open code path must not depend on a separate check catching
    # the input first. FAIL CLOSED: emit no chain, exit 9 (distinct from 3 = "no chain for
    # tier", so the two causes stay tellable apart).
    echo "[fleet-droid] resolve: WORK-CLASS-MISSING: ticket $rtfile declares no work_class. Detention, gateway capped-exclusion and the cost cap ALL scope by work_class, so NONE of them can run. FAIL CLOSED: emitting no chain (this used to emit the FULL unfiltered chain behind a note that could not go RED). Add a work_class: field." >&2
    exit 9
  fi
  # Resolve via the SINGLE shared resolver (reorder + detention + capped filter + cost-band
  # spill-up), the SAME function the main claim loop below calls — production path == test path,
  # so a test can observe exactly what the loop would do (including spill-up to a higher band).
  if rkept="$(resolve_runnable_chain "$rwc" "$rcanon")"; then
    echo "$rkept"; exit 0
  else
    echo "[fleet-droid] resolve: NO runnable model for work_class '$rwc' at cost band '$rcanon' or ANY band spill-up was allowed to reach (all detained/capped, or the COST-CAP refused a costlier band — see the COST-CAP line above) — needs escalation or a heavily-tested run/override." >&2
    exit 7
  fi
fi

TIER=""; WAIT_MIN=3; RETRIES=6; PATIENCE=1; SERIAL_JUSTIFIED=""; ONLY_TICKET=""
# PUSH MODE (DROID-BRIDGE-REGISTER). off = today's pull loop, BYTE-IDENTICAL and still the
# DEFAULT. See the block after the gateway preflight for the full rationale.
PUSH_MODE=off; TICK_S="${DROID_TICK_S:-60}"
while [ $# -gt 0 ]; do case "$1" in
  --wait)     WAIT_MIN="${2:?--wait needs minutes}"; shift 2;;
  --retries)  RETRIES="${2:?--retries needs a count}"; shift 2;;
  --patience) PATIENCE="${2:?--patience needs a cycle count}"; shift 2;;
  # HARD PIN: this tab considers ONLY the named ticket (via CLAIM_ONLY -> claim.sh). The deterministic
  # "pin a droid to a named ticket" mechanism. Pair with `--wait 0` for a one-shot pinned run.
  --only)     ONLY_TICKET="${2:?--only needs a ticket id}"; shift 2;;
  # F46 PARALLELIZABILITY-GATE escape hatch: justifies a SERIAL launch of a claimed ticket
  # that the gate would otherwise refuse (splittable: difficulty>=M AND >1 owned surface,
  # not yet decomposed). Applies to whatever this tab claims next — a per-run override, not
  # a per-ticket record; prefer 'serial_justified: <reason>' on the ticket for a durable one.
  --serial-justified=*) SERIAL_JUSTIFIED="${1#*=}"; shift;;
  # PUSH MODE, opt-in. --push = HYBRID (accept a manager dispatch, otherwise free-claim
  # exactly as today). --push-only = the "idles until told" droid the operator asked for:
  # never free-claims. Neither is the default; a tab launched as today behaves as today.
  --push)      PUSH_MODE=hybrid; shift;;
  --push-only) PUSH_MODE=only;   shift;;
  --tick)      TICK_S="${2:?--tick needs seconds}"; shift 2;;
  frontier|strong|economy|opus|sonnet|haiku|low|med|high) TIER="$1"; shift;;       # arg allowlist: canonical (frontier/strong/economy) + legacy
  *) usage;;
esac; done
[ -n "$TIER" ] || usage
# WORK-LEASE auto-wire: ensure the commit-boundary hooks are installed (idempotent; never blocks
# launch). A fresh checkout is thus NOT inert — the gate fires without a manual `install` step.
bash "$FLEET/work-lease.sh" ensure >/dev/null 2>&1 || true
# Export the hard-pin to claim.sh (empty = normal free-claim). See --only above.
export CLAIM_ONLY="$ONLY_TICKET"
# OFF-CLAUDE tier resolution: turn the tier arg into a GATEWAY model FAILOVER CHAIN (charon/<id>),
# NOT an Anthropic model. `charon tier resolve` only exposes an ANTHROPIC executor (its tier members
# are haiku/sonnet/opus) and config has NO tier->gateway-model map, so the per-tier chain lives in a
# small DATA FILE: fleet/tier-models.tsv (tier <TAB> comma,separated,failover,chain). Swap models by
# editing that file — zero code edits. The chain feeds $CHARON_AGENT_CMD's cross-model failover.
# ⚠️ PROVISIONAL defaults only — NO workhorse-per-tier is finalized; the real per-tier model is a
# PENDING OPERATOR DECISION (see the file header + memory: charon-no-workhorse-finalized).
TIER_MODELS_FILE="${CHARON_TIER_MODELS:-$FLEET/tier-models.tsv}"
# normalize + resolve via the SAME helpers the per-ticket detention filter + `resolve` hook use.
CANON="$(canon_tier "$TIER")"
models_line="$(tier_chain "$CANON")"
if [ -z "$models_line" ]; then
  echo "[fleet-droid] FATAL: no gateway model chain for tier '$TIER' (canonical '$CANON') in $TIER_MODELS_FILE — add a '$CANON<TAB>model1,model2' row." >&2
  exit 3
fi
IFS=',' read -r -a MODELS <<<"$models_line" || true
[ "${#MODELS[@]}" -gt 0 ] || { echo "[fleet-droid] FATAL: empty gateway model chain for tier '$CANON'." >&2; exit 3; }
DROID="$TIER-$$"; current=""; empties=0
# COMMIT-ACTOR-STAMP: every commit made anywhere in THIS droid's process tree (launcher
# auto-commit, the work client, the model itself) is attributed to this droid id instead of the
# indistinguishable `sim <sim@sim>`. Exported once here so it is inherited, never per-command.
source "$FLEET/droid-identity.sh"
droid_git_identity "$DROID" >/dev/null
echo "[$DROID] git identity: $GIT_COMMITTER_NAME <$GIT_COMMITTER_EMAIL> (commits are attributable to this droid)"

# ── SESSION-REPORT-WIRE: launcher's emit_session_report helper ────────────────────────────────
# The SESSION REPORT v1 block (format: fleet/SESSION-REPORT-FORMAT.md; validator:
# fleet/check-session-report.sh) is BUILT BUT INERT for droids: the format spec exists, the
# validator exists, but JOIN-PROMPT never asked for it and fleet-droid.sh never wrote it. Every
# droid log carries zero reports, and the only thing keeping the format alive is ~7 hand-pasted
# mentions in prompts/*.md.
#
# This helper closes that gap by DERIVING ~11 of the 16 fields MECHANICALLY from facts the
# launcher already holds (the ticket id, the droid+model chain, the gate's real exit code, git
# diff vs base_ref, the CHARON_RUN_RESULT from charon-run.sh). The remaining ~5 (OBSERVABLE, RAN,
# READ, BRIEF-ERRORS, NEXT) are JUDGMENT fields — the launcher asks the model for ONLY those five
# (see the appended REPORT BACK section in JOIN-PROMPT.md) and the model writes them to a
# judgment file under state/judgment/. A missing judgment file is filled with NOT-REPORTED —
# explicit, greppable, never a silent blank line.
#
# WHY THIS BEATS BLOCK-OR-WARN:
#   - Cannot strand work: the launcher writes the report from facts it already holds, so a model
#     that flubs the format costs 5 judgment fields, not a landed ticket.
#   - Not advisory: every mechanical field is grounded in git / the gate's actual exit code /
#     the outlog's actual CHARON_RUN_RESULT — a droid can no longer self-report `GATE: PASS`
#     over a red gate (the highest-value class of self-report lie, ~12 corpus incidents).
#   - Cheaper per session: 5 lines asked instead of 16, from often-weak models.
#
# ANTI-OVER-BLOCK: a droid that emits a FULL valid v1 block of its own keeps its judgment fields
# VERBATIM — the launcher does NOT clobber them. If the model-emitted block contradicts a derived
# fact, BOTH are recorded and the conflict is flagged (e.g. self-reported `STATUS: DONE` over a
# derived `GATE: FAIL` lands in the conflict list verbatim, the highest-value signal this wire
# can produce — feed it to auto-log-model-lies).
#
# RED-PROOF strategy: every test that "reverts the derivation" is asserting the field is
# DERIVED, not echoed. Harcoding `GATE: PASS` would invert the test direction; the field is
# computed from $GATE_EXIT at call time.
#
# Inputs (exported vars at call time):
#   $id              the ticket id (also the worktree id)
#   $DROID           the droid id
#   $branch          the per-ticket branch
#   $wt              the per-ticket worktree path
#   $REPO            the target repo path
#   $base_ref        the base ref (origin/master | origin/main)
#   $FIRST_MODEL     the first model in the gateway chain (== model that ran, when no failover)
#   $CHARON_RUN_RESULT  SUCCESS|EXHAUSTED|PREREQ-MISSING (parsed from the outlog)
#   $GATE_EXIT       the gate's REAL exit code (run by the launcher itself just before submit)
#   $TICKET_OWNS     the ticket's owns: field (a comma-separated list of allowed paths)
#   $STATUS          derived status from the droid outcome (DONE|BLOCKED|REFUSED|PARTIAL)
#   $outlog          the model's transcript path
# Side effects:
#   Writes the report block to $FLEET/state/reports/<DROID>-<id>.md (machine-greppable; survives
#   tab close; travels with the work).
#   Echoes the report block on stdout (so the caller can append it to a PR body).
emit_session_report(){
  local id="$1" droid="$2" branch="$3" wt="$4" repo="$5" base_ref="$6"
  local first_model="$7" charon_result="$8" gate_exit="$9"
  local owns_list="${10}" status_val="${11}" outlog="${12}"
  local FLEET_DIR="${FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
  local reports_dir="$FLEET_DIR/state/reports"
  mkdir -p "$reports_dir" "$FLEET_DIR/state/judgment" 2>/dev/null || true

  # ── Derive the 11 mechanical fields from launcher-side facts ────────────────────────────────
  # TICKET — claimed ticket id (the launcher's own fact).
  local f_ticket="$id"

  # SESSION — droid id | model that ran (== first model in chain when no failover; charon-run.sh
  # appends `CHARON_RUN_RESULT_FIRST_MODEL=$FIRST_MODEL` to the outlog on SUCCESS — the live
  # fact the launcher reads instead of trusting the model).
  local ran_model="$first_model"
  if [ -n "$outlog" ] && [ -r "$outlog" ]; then
    local parsed=""
    parsed="$(grep -E '^CHARON_RUN_RESULT_FIRST_MODEL=' "$outlog" 2>/dev/null | tail -1 | sed 's/^CHARON_RUN_RESULT_FIRST_MODEL=//')"
    [ -n "$parsed" ] && ran_model="$parsed"
  fi
  local f_session="$droid | $ran_model"

  # STATUS — derived from the droid outcome, NOT echoed from the model. A model that emits
  # STATUS: DONE in its self-report while the gate went red lands in the CONFLICT block, not in
  # the derived STATUS line.
  local f_status="$status_val"
  case "$f_status" in DONE|BLOCKED|REFUSED|PARTIAL) ;; *) f_status="REFUSED — launcher's status mapping missing" ;; esac

  # COMMIT — the worktree HEAD sha if it has commits beyond base, else 'none'. _lg_unlanded_count
  # returns the unique-commits count for $branch vs $base_ref; if >0, that count IS our commit
  # evidence. Re-derive SHA from `git rev-parse $branch` (NOT HEAD — the worktree may have the
  # auto-commit on top of the branch tip).
  local f_commit="none" commit_sha=""
  if [ -d "$wt" ]; then
    commit_sha="$(git -C "$wt" rev-parse "$branch" 2>/dev/null || true)"
    if [ -n "$commit_sha" ]; then f_commit="$commit_sha"; fi
  fi

  # FILES — `git diff --name-only $base_ref..$branch` against the WORKTREE (the leak-guard's own
  # fact pattern). Count + comma-separated paths, capped at 20 paths for token-leanness (the
  # report file itself holds the full list when it's longer; we keep the report one-line).
  local f_files="0 changed:" f_files_full=""
  if [ -d "$wt" ]; then
    local -a _paths=()
    while IFS= read -r p; do [ -n "$p" ] && _paths+=("$p"); done \
      < <(git -C "$wt" diff --name-only "$base_ref..$branch" 2>/dev/null | head -200)
    f_files_full="$(printf '%s\n' "${_paths[@]:-}" | paste -sd',' - 2>/dev/null || true)"
    local fc=${#_paths[@]}; f_files="$fc changed: $f_files_full"
  fi

  # OWNS-OK — every diff path that is NOT in $owns_list and is NOT the per-ticket review-log
  # fragment is an owns violation. Output `yes` when clean, `NO — <offender>` otherwise. The
  # ticket's owns: list is comma-separated; we split and member-test each diff path.
  local f_owns="yes"
  if [ -n "$owns_list" ] && [ -d "$wt" ]; then
    local offender=""
    local -a _allowed=()
    IFS=',' read -r -a _allowed <<<"$owns_list" || true
    while IFS= read -r p; do
      [ -z "$p" ] && continue
      # The droid's review-log fragment is always allowed (per JOIN-PROMPT step 4).
      case "$p" in "docs/review-log/$id.md") continue ;; esac
      local ok=0 a
      for a in "${_allowed[@]}"; do [ "$a" = "$p" ] && ok=1 && break; done
      if [ "$ok" -eq 0 ]; then offender="$p"; break; fi
    done < <(git -C "$wt" diff --name-only "$base_ref..$branch" 2>/dev/null)
    if [ -n "$offender" ]; then f_owns="NO — $offender is owned by $id"; fi
  elif [ -z "$owns_list" ]; then
    f_owns="yes (no owns: declared)"
  fi

  # GATE — the REAL exit code of the gate the launcher ran just before submit. NOT self-report.
  # $gate_exit is the integer from running $RR_GATE in the worktree (the launcher's own
  # observation). 0 -> PASS, anything else -> FAIL with the exit code surfaced.
  local f_gate
  if [ "$gate_exit" -eq 0 ] 2>/dev/null; then f_gate="PASS"
  else f_gate="FAIL — gate exit code $gate_exit"
  fi

  # TESTS — best-effort parse of `pytest -q` summary from the most recent transcript. The gate
  # itself emits ruff/mypy/check_boundary/check_version output too, but pytest is the only one
  # that has a "<n> passed, <n> failed" tally worth reporting here. When we can't parse, the
  # field reports `n/a — <why>` so a missing parse is never a silent PASS.
  local f_tests="n/a — gate output not parsed"
  if [ -r "$outlog" ]; then
    local tally=""
    tally="$(grep -oE '[0-9]+ passed|[0-9]+ failed|[0-9]+ skipped' "$outlog" 2>/dev/null | tail -10)"
    if [ -n "$tally" ]; then f_tests="$tally"; fi
  fi

  # RED-PROOF — best-effort parse of TWO distinct exit codes from the outlog: a "broken" run and
  # a "green" run. We look for the join prompt's gate command (pytest summary + ruff + mypy +
  # check_boundary + check_version) and for the project's own test commands. ANY two distinct
  # exit codes in the outlog let us claim red-then-green; the launcher's own gate run is the
  # canonical green, so a pre-launch red is what we search the transcript for. NOT-DONE when
  # nothing parseable is found.
  local f_redproof="NOT-DONE"
  if [ -r "$outlog" ]; then
    local broken_rc="" green_rc="$gate_exit"
    # Heuristic: any test/ruff/mypy/boundary/version line with a non-zero exit in the tail. The
    # model typically prints the gate command and its result before its first commit; the first
    # "broken" pass is the one that REVERSED into the fix.
    broken_rc="$(grep -oE 'gate RED\b|exit code [0-9]+|rc=[0-9]+' "$outlog" 2>/dev/null | grep -oE '[0-9]+' | sort -u | grep -v "^${green_rc:-0}$" | head -1)"
    if [ -n "$broken_rc" ] && [ -n "$green_rc" ]; then
      f_redproof="broken=$broken_rc green=$green_rc"
    fi
  fi

  # BLOCKED-BY — none (the droid ran), unless the launcher recorded a hard blocker. The
  # parallelizability-gate + work-lease + capped-filter + cost-cap SKIPs above all set $current
  # back to empty without reporting; for those, BLOCKED-BY names the gate that refused (greppable).
  local f_blocked="none"
  case "$f_status" in
    REFUSED) f_blocked="$status_val — see launch-path SKIP lines above" ;;
    BLOCKED) f_blocked="see launch-path messages" ;;
  esac

  # BUDGET — best-effort parse of the model's transcript for a budget-exhaustion signal. The
  # `ResourceExhausted: Worker local total request limit reached` shape (opencode's own quota
  # message) is the highest-value match: a session that ran out of requests is the canonical
  # "claim STATUS: DONE while silently truncated" failure.
  local f_budget="ok"
  if [ -r "$outlog" ] && grep -qE 'ResourceExhausted|rate.?limit|quota exceeded|insufficient (funds|credit|balance)|session limit|no capacity|out of (credit|quota)|request limit' "$outlog" 2>/dev/null; then
    f_budget="TRUNCATED — see $outlog for the provider/rate signal"
  fi
  # If the launcher hit the gate's own budget (e.g. timeout), surface it too. The gate's exit
  # code is 124 when the gate's `timeout` wrapper fired (when RR_GATE includes one).
  if [ "$gate_exit" -eq 124 ] 2>/dev/null && [ "$f_budget" = "ok" ]; then
    f_budget="TRUNCATED — gate TIMEOUT (rc=124) — see $outlog"
  fi

  # ── Read the 5 JUDGMENT fields the model wrote to its judgment file (or NOT-REPORTED) ─────
  local judgment_file="$FLEET_DIR/state/judgment/$droid-$id.md"
  # Initialise to empty (NOT unset) so the `set -u` reads below don't trip unbound-variable.
  local j_observable="" j_ran="" j_read="" j_brief="" j_next=""
  if [ -r "$judgment_file" ]; then
    # sub(/^[^:]*: +/, "") strips "<FIELD>: " AND any extra leading whitespace the model may
    # have added — the format spec pads to align with sibling fields, so a value like
    # "OBSERVABLE:   MET" arrives with a 2-3 space prefix that has to go.
    j_observable="$(awk -F': ' '$1=="OBSERVABLE"   {sub(/^[^:]*: +/, "");print;exit}' "$judgment_file")"
    j_ran="$(awk -F': ' '$1=="RAN"          {sub(/^[^:]*: +/, "");print;exit}' "$judgment_file")"
    j_read="$(awk -F': ' '$1=="READ"         {sub(/^[^:]*: +/, "");print;exit}' "$judgment_file")"
    j_brief="$(awk -F': ' '$1=="BRIEF-ERRORS" {sub(/^[^:]*: +/, "");print;exit}' "$judgment_file")"
    j_next="$(awk -F': ' '$1=="NEXT"         {sub(/^[^:]*: +/, "");print;exit}' "$judgment_file")"
  fi
  [ -n "$j_observable" ] || j_observable="NOT-REPORTED"
  [ -n "$j_ran" ]        || j_ran="NOT-REPORTED"
  [ -n "$j_read" ]       || j_read="NOT-REPORTED"
  [ -n "$j_brief" ]      || j_brief="NOT-REPORTED"
  [ -n "$j_next" ]       || j_next="NOT-REPORTED"

  # ── ANTI-OVER-BLOCK + CONFLICT: detect a self-reported v1 block in the model outlog ────────
  # If the model ALSO emitted a complete v1 block of its own, we keep BOTH. STATUS is the most
  # load-bearing field for conflict detection — a model reporting DONE while the gate is RED is
  # the signature self-report lie. We do NOT silently prefer one over the other.
  local model_block="" model_status="" model_gate=""
  if [ -r "$outlog" ]; then
    model_block="$(awk '/^=== SESSION REPORT v1 ===$/{flag=1;next}/^=== END REPORT ===$/{flag=0}flag' "$outlog" 2>/dev/null)"
  fi
  if [ -n "$model_block" ]; then
    model_status="$(printf '%s\n' "$model_block" | awk -F': ' '$1=="STATUS" {sub(/^[^:]*: +/, "");print;exit}')"
    model_gate="$(printf '%s\n' "$model_block" | awk -F': ' '$1=="GATE" {sub(/^[^:]*: +/, "");print;exit}')"
  fi
  local conflict_note=""
  # STATUS and GATE are the two fields where a model lie is most damaging: STATUS flips whether
  # the work is "done" and GATE flips whether the gate was green. ANY disagreement between
  # model-self-report and launcher-derived truth on EITHER field produces a flag — silent
  # overwrite of either side is RED. Both blocks are still kept verbatim (anti-over-block);
  # the flag is the audit trail, not a re-write.
  local conflict_bits=()
  if [ -n "$model_status" ] && [ "$model_status" != "$f_status" ]; then
    conflict_bits+=("STATUS: model='$model_status' derived='$f_status'")
  fi
  if [ -n "$model_gate" ] && [ "$model_gate" != "$f_gate" ]; then
    conflict_bits+=("GATE: model='$model_gate' derived='$f_gate' (real exit code $gate_exit)")
  fi
  if [ "${#conflict_bits[@]}" -gt 0 ]; then
    conflict_note="CONFLICT on $(IFS=', '; echo "${conflict_bits[*]}") — both kept; the self-report line is the lie class (feed to auto-log-model-lies)."
  fi

  # ── Compose the canonical v1 block ─────────────────────────────────────────────────────────
  local report_path="$reports_dir/$droid-$id.md"
  {
    echo "=== SESSION REPORT v1 ==="
    printf 'TICKET:       %s\n'         "$f_ticket"
    printf 'SESSION:      %s\n'         "$f_session"
    printf 'STATUS:       %s\n'         "$f_status"
    printf 'COMMIT:       %s\n'         "$f_commit"
    printf 'FILES:        %s\n'         "$f_files"
    printf 'OWNS-OK:      %s\n'         "$f_owns"
    printf 'GATE:         %s\n'         "$f_gate"
    printf 'TESTS:        %s\n'         "$f_tests"
    printf 'RED-PROOF:    %s\n'         "$f_redproof"
    printf 'OBSERVABLE:   %s\n'         "$j_observable"
    printf 'RAN:          %s\n'         "$j_ran"
    printf 'READ:         %s\n'         "$j_read"
    printf 'BRIEF-ERRORS: %s\n'         "$j_brief"
    printf 'BLOCKED-BY:   %s\n'         "$f_blocked"
    printf 'BUDGET:       %s\n'         "$f_budget"
    printf 'NEXT:         %s\n'         "$j_next"
    echo "=== END REPORT ==="
    # Append the model's self-reported block (if any) verbatim — the manager reads both. A
    # CONFLICT line is appended only when the model block disagrees with the derived one.
    if [ -n "$model_block" ]; then
      echo
      echo "--- MODEL SELF-REPORT BLOCK (kept verbatim; NOT-REPORTED-safe) ---"
      printf '%s\n' "$model_block"
      if [ -n "$conflict_note" ]; then
        echo
        printf 'MODEL-LIE-FLAG: %s\n' "$conflict_note"
      fi
    fi
  } > "$report_path"

  # Echo to stdout so the caller can append to the PR body.
  cat "$report_path"
}
# Release the in-flight claim + stand-down the worktree on Ctrl-C / exit (DROID-LIFECYCLE-REAP).
# GUARANTEES (no data loss — accepted criteria):
#   1. Uncommitted changes in the worktree are AUTO-COMMITTED (with a flagging message) BEFORE
#      the worktree is removed. The commit lives on the branch, so worktree removal cannot
#      destroy it. A `git stash` was considered and rejected: stashes are easy to forget,
#      and a forgotten stash is silent data loss. An auto-commit at stand-down is loud + on
#      the branch (the manager can always see and undo it).
#   2. The worktree dir is removed with `git worktree remove` (NO --force needed; the
#      auto-commit above guarantees a clean tree). If even that fails, fall back to
#      `safe_worktree_remove` which honors the needs-push guard (committed-but-unlanded work).
#   3. The branch itself is NEVER `git branch -D`'d by this cleanup — the only data-loss path
#      the manager hit this session. Worktree removal keeps the branch. A subsequent
#      `leak_worktree_setup` re-claim will REUSE the branch via the P0 #4 guard.
#   4. The claim marker is released so a fresh droid can re-claim — but ONLY when no worktree
#      work was preserved. If we auto-committed, the claim stays open AND we mark
#      state/needs-push/<id> so the manager (or the reaper) lands it.
# SIGKILL / terminal-close bypass: the bash trap does NOT fire for those — the OUT-OF-BAND
# reaper (fleet/reap-orphans.sh, wired into foreman) handles those cases. cleanup() only
# runs when the shell actually exits.
cleanup(){
  # PUSH MODE: leave the board on a CLEAN exit so an idle row never outlives the tab.
  # This is the tidy path only — a droid that is killed hard never reaches it, and that is
  # intentional: the bridge's own lease expiry + graduated purge (daemon.py) is the single
  # source of truth for "this droid is dead", and DROID-LIFECYCLE-REAP consumes THAT signal.
  # Adding a second liveness notion here is exactly what the constraint forbids.
  if [ "${PUSH_MODE:-off}" != off ] || [ -n "${BRIDGE_LEASE:-}" ]; then
    bash "${BRIDGE:-$FLEET/droid-bridge.sh}" unregister "$DROID" >/dev/null 2>&1 || true
  fi
  if [ -n "${current:-}" ] && [ ! -e "$FLEET/state/submitted/$current" ]; then
    bash "$FLEET/release.sh" "$current" >/dev/null 2>&1 || true; fi
  # Drop this run's loop-guard counters (per-run scratch); durable quarantine markers under
  # state/loop-guard/<id> PERSIST for the manager to inspect + clear.
  rm -rf "$FLEET/state/loop-guard/runs/$DROID" 2>/dev/null || true
  # If we have an active claim AND the worktree exists, stand-down safely. The branch is
  # never deleted by this path (worktree removal preserves it; leak-guard's P0 #4 reuses it
  # on re-claim).
  if [ -n "${current:-}" ] && [ -n "${wt:-}" ] && [ -d "$wt" ] && [ -d "$REPO" ]; then
    # (1) AUTO-COMMIT any uncommitted changes BEFORE removal. A `git stash` was an option
    #     but a forgotten stash = silent data loss; an auto-commit is on the branch, loud,
    #     and trivially undoable (`git reset HEAD~1`). Flag the message so the manager
    #     can audit for half-done work.
    if [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]; then
      echo "[$DROID] cleanup: $current has uncommitted changes — auto-committing (droid stood down without committing)." >&2
      git -C "$wt" add -A
      git -C "$wt" commit -q -m "chore($current): cleanup auto-commit — droid stood down without committing (review for completeness)" || true
      # Flag for the manager / reaper: the auto-commit is on the branch, but the droid
      # went away — a re-claim could clobber it (the P0 #4 guard prevents clobber, but
      # this marker keeps needs-push-style visibility until the manager lands the branch).
      mkdir -p "$FLEET/state/needs-push"
      printf 'branch=%s\nworktree=%s\nrepo=%s\nreason=cleanup auto-commit (droid stood down with uncommitted work)\nflagged=%s\n' \
        "$branch" "$wt" "$REPO" "$(date -u +%FT%TZ)" > "$FLEET/state/needs-push/$current" || true
    fi
    # (2) SAFELY remove the worktree — branch STAYS. A leak-guard REFUSAL IS TERMINAL.
    #
    #     THE BUG THIS REPLACES (CRITICAL, reproduced): this read
    #       `if ! safe_worktree_remove … 2>/dev/null; then worktree remove --force || rm -rf; fi`
    #     The `if !` INVERTED the guard into a trigger. safe_worktree_remove returns non-zero
    #     EXACTLY and ONLY when the target must not be destroyed — live needs-push marker,
    #     uncommitted changes, commits not on any remote, a catastrophic target ($HOME, `/`,
    #     the live checkout, a worktree-family root), or a path it cannot prove is ours — and
    #     the `||` chain then destroyed it anyway with the bluntest tool available. `2>/dev/null`
    #     silenced the refusal so it was invisible. Worse, step (1) above WRITES the
    #     state/needs-push marker that is the first thing the guard refuses on, so the most
    #     common stand-down path armed its own override.
    #
    #     Same shape as fleet/retire-done.sh:74-77 — call it, act only on success, and let a
    #     refusal simply leave the worktree alone. stderr is NOT suppressed: the refusal message
    #     names the reason and the manager needs to see it.
    if safe_worktree_remove "$REPO" "$wt" "$current" "$FLEET/state/needs-push"; then
      git -C "$REPO" worktree prune 2>/dev/null || true
    else
      echo "[$DROID] cleanup: worktree KEPT: $wt — leak-guard REFUSED removal (reason above). Branch '$branch' and its work are preserved; resolve by hand." >&2
    fi
  fi
}
# ── GATEWAY / TOKEN PREFLIGHT — PRE-CLAIM (DROID-CLIENT-PREFLIGHT, instance 2) ───────────────────
# SAME CLASS as the PATH fix at the top of this file: the launcher trusted the INVOKING SHELL'S
# ENVIRONMENT instead of DERIVING what it needs. PATH was instance 1; the gateway bearer token is
# instance 2, and worse — the code already documented the right answer and nobody wired it.
#
# WHAT WENT WRONG (real incident, 2026-07-25): a PowerShell-invoked, non-interactive bash inherited
# no CHARON_GATEWAY_TOKEN. capability/availability.py reads the token from the AMBIENT ENV ONLY
# (its GATEWAY_TOKEN_ENVS tuple), so its unauthenticated GET /charon/status came back 302 with a
# ZERO-BYTE body -> json.loads("") -> "Expecting value: line 1 column 1 (char 0)". The capped-filter
# then FAILED CLOSED and DETAINED the ticket. That fail-closed is CORRECT and is deliberately left
# untouched. The defect is that it fired PER TICKET: claim -> detain -> re-claim -> quarantine, and
# it chewed through FIVE tickets before the operator killed the tab.
#
# A token/gateway fault is a STARTUP condition, not a per-ticket one. Detect it ONCE, here, BEFORE
# the claim loop, and stand down with a distinct code — instead of burning the board into quarantine
# one ticket at a time. Placed before the cleanup traps so a preflight exit is clean (nothing has
# been claimed, no worktree exists, so there is nothing to clean up).
#
# TOKEN DERIVATION: env-registry.sh:bearer_token() is the ONE canonical reader
# (~/.config/opencode/opencode.json -> provider.charon.options.apiKey). Sourced through its source
# guard in a COMMAND-SUBSTITUTION SUBSHELL, so neither its `set -uo pipefail` nor its FLEET/OUTPUT/
# GATEWAY_URL variables can leak into this script. env-registry.sh's own header states the rule this
# implements: "CHARON_GATEWAY_TOKEN (shell env) is documented STALE ... always re-derive from the
# live opencode config". So the DERIVED value WINS; a disagreeing shell var is reported as drift
# (same notion of drift as preflight.sh:detect_gateway_token_drift) and overridden, never obeyed.
GW_URL="${CHARON_GATEWAY_URL:-http://10.0.1.60:8080}"
derive_gateway_token   # (defined near the top; also called before the `resolve` hook)

# PROVE the gateway is actually readable with that token, right now. The failure signature we are
# defending against is NOT an HTTP error code — an unauthenticated /charon/status answers 302 with an
# EMPTY BODY, which curl reports as success. So the test is "does the body parse as a JSON object",
# which is exactly what availability.py needs and exactly what blew up.
_gw_body="$(curl -sS --max-time 8 \
              -H "Authorization: Bearer ${CHARON_GATEWAY_TOKEN:-}" \
              -H 'Accept: application/json' \
              "$GW_URL/charon/status" 2>/dev/null || true)"
if ! printf '%s' "$_gw_body" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if isinstance(d,dict) else 1)' 2>/dev/null; then
  _tok_state="derived from ${CHARON_OPENCODE_CONFIG:-$HOME/.config/opencode/opencode.json}"
  [ -n "$_derived_tok" ] || _tok_state="EMPTY — no token could be derived, and none was inherited"
  {
    echo "[fleet-droid] FATAL: gateway /charon/status is NOT READABLE — standing down BEFORE claiming any ticket."
    echo "[fleet-droid]   gateway:   $GW_URL/charon/status"
    echo "[fleet-droid]   token:     $_tok_state"
    echo "[fleet-droid]   response:  ${#_gw_body} bytes, not a JSON object (an unauthenticated"
    echo "[fleet-droid]              /charon/status answers 302 with a 0-byte body — that is this signature)."
    echo "[fleet-droid]   WHY THIS IS FATAL AT STARTUP: the capped-filter fails closed and DETAINS work when"
    echo "[fleet-droid]              it cannot read gateway state. Continuing would claim, detain and"
    echo "[fleet-droid]              QUARANTINE ticket after ticket. ZERO tickets were claimed."
    echo "[fleet-droid]   FIX: set provider.charon.options.apiKey in"
    echo "[fleet-droid]        ${CHARON_OPENCODE_CONFIG:-$HOME/.config/opencode/opencode.json}, or bring \$GW_URL back up."
  } >&2
  exit 5
fi
unset _derived_tok _env_tok _gw_body _tok_state

# ── PUSH MODE: register on the session-bridge (DROID-BRIDGE-REGISTER) ────────────────────────────
# Operator ask: "a version of a droid which IDLES until the MANAGER/SUPERVISOR session sends them
# work." Today droids PULL. This adds PUSH, as WIRING over primitives that already exist — see
# fleet/droid-bridge.sh for the reuse table (nudge + board-poll + idempotency.py, no daemon change).
#
# ADDITIVE AND OPT-IN, deliberately not the default. Registering every tab by default would make the
# whole pool depend on a daemon that is NOT yet supervised (SERVICE-LIVENESS-WATCHDOG owns that) and
# has already died once to a reboot. `fleet-droid.sh <tier>` with no push flag makes ZERO bridge
# calls and behaves byte-identically to before.
#
# BOUNDARY (manager-never-spawns-droids): the manager only ever dispatches to an ALREADY-RUNNING
# droid. The operator opens tabs. Nothing here spawns anything.
BRIDGE="$FLEET/droid-bridge.sh"
BRIDGE_LEASE=""; BRIDGE_REPO="${CHARON_BRIDGE_REPO:-charon}"; PUSH_DEGRADED=0
if [ "$PUSH_MODE" != off ]; then
  if BRIDGE_LEASE="$(bash "$BRIDGE" register "$DROID" "$DROID" "$BRIDGE_REPO" pending 2>/dev/null)" \
     && [ -n "$BRIDGE_LEASE" ]; then
    echo "[$DROID] push mode '$PUSH_MODE': registered on the session-bridge as '$DROID' (repo=$BRIDGE_REPO, tick=${TICK_S}s)."
  else
    # FAIL-CLOSED ON WORK, LOUD ALWAYS — and the two modes diverge on purpose.
    if [ "$PUSH_MODE" = only ]; then
      # A push-only droid with no bridge has NO way to ever receive work. Spinning silently is
      # precisely the failure that hid a dead grader for nine days, so stand down NOW, nonzero,
      # with a durable marker. Exit 6, not the design's suggested 3: 3 is already taken above by
      # the "no gateway model chain for tier" FATAL, and a code that means two things is a code
      # that means nothing.
      mkdir -p "$FLEET/state/push-degraded" 2>/dev/null || true
      printf '%s\tpush-only\tbridge-unreachable\n' "$(date -u +%FT%TZ)" > "$FLEET/state/push-degraded/$DROID" 2>/dev/null || true
      {
        echo "[$DROID] FATAL: BRIDGE-DOWN — --push-only cannot receive work with no bridge."
        echo "[$DROID]   A push-only droid has no pull fallback BY DESIGN, so idling here would be"
        echo "[$DROID]   indistinguishable from a dead tab. Standing down loudly instead."
        echo "[$DROID]   marker: $FLEET/state/push-degraded/$DROID"
        echo "[$DROID]   Use --push (hybrid) to degrade to pull instead of standing down."
      } >&2
      exit 6
    fi
    # Hybrid: the manager may be gone, but the board is not. Degrade to pull — LOUDLY, and with a
    # marker, so "it kept working" never means "nobody noticed the bridge died".
    PUSH_DEGRADED=1; PUSH_MODE=off
    mkdir -p "$FLEET/state/push-degraded" 2>/dev/null || true
    printf '%s\thybrid\tbridge-unreachable-degraded-to-pull\n' "$(date -u +%FT%TZ)" > "$FLEET/state/push-degraded/$DROID" 2>/dev/null || true
    {
      echo "[$DROID] BRIDGE-DOWN: could not register on the session-bridge."
      echo "[$DROID]   DEGRADING TO PULL for this run — dispatches cannot be received, free-claim continues."
      echo "[$DROID]   marker: $FLEET/state/push-degraded/$DROID"
    } >&2
  fi
fi

trap 'cleanup; echo "[$DROID] stood down."; exit 130' INT TERM
trap cleanup EXIT
# ── PUSH-MODE HELPERS ────────────────────────────────────────────────────────────────────────────
# The tick IS the heartbeat: droid-bridge.sh's `poll` calls board(session_id=…), which the daemon
# answers by refreshing this session's 600s lease. So an idling droid proves liveness for free, and
# a droid that DIES stops refreshing and expires into the daemon's own graduated purge. There is no
# second liveness notion here — that is the point.
bridge_fails=0
push_bridge_down(){
  bridge_fails=$((bridge_fails+1))
  mkdir -p "$FLEET/state/push-degraded" 2>/dev/null || true
  printf '%s\t%s\tbridge-unreachable (tick %s)\n' "$(date -u +%FT%TZ)" "$PUSH_MODE" "$bridge_fails" \
    > "$FLEET/state/push-degraded/$DROID" 2>/dev/null || true
  if [ "$PUSH_MODE" = only ]; then
    echo "[$DROID] BRIDGE-DOWN (consecutive tick $bridge_fails) — --push-only has NO pull fallback by design." >&2
    if [ "$RETRIES" -gt 0 ] && [ "$bridge_fails" -ge "$RETRIES" ]; then
      echo "[$DROID] FATAL: BRIDGE-DOWN for $bridge_fails consecutive ticks — standing down (exit 6). marker: $FLEET/state/push-degraded/$DROID" >&2
      exit 6
    fi
  else
    echo "[$DROID] BRIDGE-DOWN — DEGRADING TO PULL for the rest of this run (free-claim continues; dispatches cannot arrive). marker: $FLEET/state/push-degraded/$DROID" >&2
    PUSH_MODE=off; PUSH_DEGRADED=1
  fi
}
# ONE tick. rc 0 = a dispatch is now in $PUSH_TICKET; 1 = nothing waiting; 2 = bridge down (handled).
push_poll_once(){
  PUSH_TICKET=""; PUSH_MSGID=""
  local out rc
  out="$(bash "$BRIDGE" poll "$DROID" "$BRIDGE_REPO" 2>/dev/null)"; rc=$?
  case "$rc" in
    0) read -r PUSH_TICKET PUSH_MSGID <<<"$out"
       bridge_fails=0
       echo "[$DROID] DISPATCH received: ticket=$PUSH_TICKET (msg=$PUSH_MSGID)"
       # Ack immediately: the local idempotency ledger has already recorded this id, so the
       # server-side copy has done its job and must not be redelivered.
       [ -n "$BRIDGE_LEASE" ] && bash "$BRIDGE" ack "$DROID" "$BRIDGE_LEASE" "$PUSH_MSGID" >/dev/null 2>&1
       return 0 ;;
    1) bridge_fails=0; return 1 ;;
    *) push_bridge_down; return 2 ;;
  esac
}
# Idle on the bridge for up to <total> seconds, ticking every $TICK_S. Returns 0 the moment a
# dispatch lands (never sleeps through one), 1 if the window elapsed or push was degraded away.
push_wait(){
  local total="$1" waited=0
  while [ "$waited" -lt "$total" ]; do
    sleep "$TICK_S"; waited=$((waited+TICK_S))
    [ "$PUSH_MODE" = off ] && return 1
    if push_poll_once; then return 0; fi
  done
  return 1
}
PUSH_TICKET=""; PUSH_MSGID=""; PUSH_CARRY=""

wmsg=""; [ "$WAIT_MIN" -gt 0 ] && wmsg=", wait=${WAIT_MIN}m retries=${RETRIES} patience=${PATIENCE}"
echo "[$DROID] charon-fleet droid up (off-Claude via ${CHARON_AGENT_CMD##*/}; gateway chain=${MODELS[*]}$wmsg). Ctrl-C to stand down."
while true; do
  # ── PUSH: is the manager holding work for us? ──────────────────────────────────────────────────
  # Back to `pending` on the board first, so an idle droid is idle BY FIELD, never by inference.
  # PUSH_CARRY holds a dispatch that arrived DURING an idle window. It must survive the
  # loop-top reset: by the time push_wait returns, the message has already been consumed
  # from the queue, recorded in the idempotency ledger and acked — so clearing it here and
  # re-polling would find nothing and SILENTLY DROP the operator's work. (Caught by
  # droid-bridge.test.sh section D, which is exactly why that test dispatches into an
  # idling droid rather than a starting one.)
  if [ -n "${PUSH_CARRY:-}" ]; then
    PUSH_TICKET="$PUSH_CARRY"; PUSH_CARRY=""
  else
  PUSH_TICKET=""; PUSH_MSGID=""
  if [ "$PUSH_MODE" != off ]; then
    # ORDER MATTERS: poll BEFORE the status update. daemon.py's `update` handler runs the same
    # _process_read as `board` — it DRAINS and returns the queue too (daemon.py:507,533). Since
    # this script only wants a status change from it, a dispatch that landed just before an
    # update would be marked delivered and then thrown away, stalling it until the 120s
    # REDELIVER_WINDOW_S re-offered it. Polling first means the consuming call always gets first
    # look; only a sub-millisecond window remains, and at-least-once redelivery covers that.
    push_poll_once || true
    [ -z "$PUSH_TICKET" ] && [ -n "$BRIDGE_LEASE" ] && bash "$BRIDGE" update "$DROID" pending >/dev/null 2>&1
    # PUSH-ONLY: never free-claims. With nothing dispatched, idle ON THE BRIDGE (ticking, which is
    # also the heartbeat) rather than falling through to claim.sh.
    if [ "$PUSH_MODE" = only ] && [ -z "$PUSH_TICKET" ]; then
      if [ "$WAIT_MIN" -gt 0 ] && { [ "$RETRIES" -eq 0 ] || [ "$empties" -lt "$RETRIES" ]; }; then
        rmax="$RETRIES"; [ "$RETRIES" -eq 0 ] && rmax="∞"
        echo "[$DROID] push-only: no dispatch — idling on the bridge, tick=${TICK_S}s for ${WAIT_MIN}m (idle $((empties+1))/$rmax)…"
        if push_wait "$((WAIT_MIN*60))"; then empties=0; PUSH_CARRY="$PUSH_TICKET"; else empties=$((empties+1)); fi
        continue
      else
        echo "[$DROID] push-only: no dispatch and idle budget exhausted — standing down."; break
      fi
    fi
  fi
  fi
  # ── PER-ITERATION PIN ─────────────────────────────────────────────────────────────────────────
  # CLAIM_ONLY used to be exported ONCE at launch, which is why a dispatch could not target a
  # ticket on a RUNNING droid. It is now re-exported every iteration: a dispatched ticket pins THIS
  # iteration only, and the launch-time --only pin is restored the moment the dispatch is done.
  # NOTE what this does NOT do: it does not bypass anything. The pin only narrows what claim.sh will
  # CONSIDER; the atomic claim, the work-lease, the parallelizability gate, loop-guard and
  # leak-guard all still run exactly as they do for a pulled ticket.
  export CLAIM_ONLY="${PUSH_TICKET:-$ONLY_TICKET}"
  # Tier patience: try OWN tier first; only dip to lower tiers once we've been
  # empty-at-own-tier for >= PATIENCE wait-cycles (gives lower tiers a head start).
  mode=both; [ "$empties" -lt "$PATIENCE" ] && mode=own-only
  if ! res="$(bash "$FLEET/claim.sh" "$TIER" "$DROID" "$mode")"; then
    # A dispatch that cannot be claimed is REFUSED, not improvised around: unknown ticket id,
    # already claimed, dep-blocked, parked, quarantined or done all land here. Tell the manager
    # why and go back to idle. No branch, no worktree, no claim file is created — which is what
    # makes "no dark work" structural rather than a promise.
    if [ -n "$PUSH_TICKET" ]; then
      echo "[$DROID] DISPATCH REFUSED: '$PUSH_TICKET' is not claimable by this droid (unknown, already claimed, blocked, parked or done). Staying idle." >&2
      [ -n "$BRIDGE_LEASE" ] && bash "$BRIDGE" reply "$DROID" "${CHARON_MANAGER_SID:-manager}" \
        "REFUSED ticket=$PUSH_TICKET reason=not-claimable-by-$DROID" >/dev/null 2>&1
      continue
    fi
    if [ "$WAIT_MIN" -gt 0 ] && { [ "$RETRIES" -eq 0 ] || [ "$empties" -lt "$RETRIES" ]; }; then
      empties=$((empties+1))
      rmax="$RETRIES"; [ "$RETRIES" -eq 0 ] && rmax="∞"
      echo "[$DROID] no $TIER-eligible work — waiting ${WAIT_MIN}m (empty $empties/$rmax)…"
      # HYBRID: wait on the bridge instead of sleeping blind, so a dispatch wakes us within one
      # tick instead of up to --wait minutes. Pull is unaffected: if nothing arrives we simply
      # re-enter the same claim.sh call, exactly as the blind sleep did.
      if [ "$PUSH_MODE" != off ]; then
        # Carry a mid-window dispatch across the loop boundary — see PUSH_CARRY at the top.
        if push_wait "$((WAIT_MIN*60))"; then PUSH_CARRY="$PUSH_TICKET"; fi
      else
        sleep "$((WAIT_MIN*60))"
      fi
      continue
    fi
    echo "[$DROID] no $TIER-eligible work left — standing down."; break
  fi
  empties=0
  read -r _tag id tfile <<<"$res"; current="$id"
  if [ "$PUSH_MODE" != off ] && [ -n "$BRIDGE_LEASE" ]; then
    bash "$BRIDGE" update "$DROID" in-progress >/dev/null 2>&1
  fi
  echo "[$DROID] claimed $id — launching session…"
  # F46 PARALLELIZABILITY-GATE: refuse to launch a SPLITTABLE ticket (difficulty>=M AND >1
  # independent owned surface — see fleet/checks/parallelizability-gate.sh) as a single
  # SERIAL job unless it has already been decomposed into sub-tickets or is justified
  # (--serial-justified for this run, or a durable 'serial_justified:' field on the ticket).
  # Mechanizes the wall-clock rule (MANAGER-OPERATING-RULES.md sec.4) at the ONE place a
  # serial launch actually happens, so a splittable god-ticket can never silently run serial.
  pg_args=(check "$id"); [ -n "$SERIAL_JUSTIFIED" ] && pg_args+=(--serial-justified="$SERIAL_JUSTIFIED")
  if ! pg_out="$(bash "$FLEET/checks/parallelizability-gate.sh" "${pg_args[@]}" 2>&1)"; then
    echo "$pg_out" >&2
    echo "[$DROID] SKIP $id: PARALLELIZABILITY-GATE refused a serial launch — decompose it (fleet/decompose.sh $id) or pass --serial-justified=\"<reason>\"." >&2
    bash "$FLEET/release.sh" "$id" >/dev/null 2>&1 || true; current=""
    bash "$FLEET/loop-guard.sh" record "$id" "$DROID" >/dev/null 2>&1 \
      || echo "[$DROID] LOOP-GUARD: $id quarantined (parallelizability-gate refused repeatedly)." >&2
    continue
  fi
  # DETENTION-REDLINE + CRIPPLE #2/#3: scope the tier chain to THIS ticket's work_class (from its
  # board file) and resolve it to a RUNNABLE chain via the SAME shared resolver the `resolve` hook
  # uses — real-outcome reorder + drop HARD-detained + drop gateway-CAPPED, and SPILL UP to the next
  # cost band when the whole band is unrunnable (all detained/capped) rather than burning a ~1800s
  # timeout on a capped model or backlogging on cheap. Only when the WHOLE ladder up to frontier is
  # unrunnable do we SKIP (+ loop-guard record) — a detained/capped model never runs by fall-through.
  wclass="$(awk -F': ' '$1=="work_class"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  if [ -n "$wclass" ]; then
    if run_line="$(resolve_runnable_chain "$wclass" "$CANON")"; then
      IFS=',' read -r -a RUN_MODELS <<<"$run_line" || true
    else
      echo "[$DROID] SKIP $id: NO runnable model for work_class '$wclass' at cost band '$CANON' or ANY band spill-up was allowed to reach (all detained/capped, or the COST-CAP refused a costlier band — see the COST-CAP line above; the ticket is DETAINED and stays claimable, it will retry when a cheaper leg frees). NOT running a detained/capped model and NOT spending above the ceiling." >&2
      bash "$FLEET/release.sh" "$id" >/dev/null 2>&1 || true; current=""
      bash "$FLEET/loop-guard.sh" record "$id" "$DROID" >/dev/null 2>&1 \
        || echo "[$DROID] LOOP-GUARD: $id quarantined (no runnable model after spill-up for '$wclass')." >&2
      continue
    fi
  else
    # F4 (money guardrail): the claim-loop half of the same fail-open. A WARNING that still
    # ran the full unfiltered chain is not a guardrail — it is a log line. Refuse the ticket,
    # record WHY in the ledger, release it so it is not silently held, and quarantine it so we
    # do not spin re-claiming a ticket that can never be scoped.
    echo "[$DROID] SKIP $id: WORK-CLASS-MISSING — the ticket declares no work_class, so the detention filter, the gateway capped-exclusion and the cost cap could not scope and NONE of them ran. NOT running the full unfiltered chain (fail closed). The ticket is released and quarantined; add a work_class: field." >&2
    exhaust_led "ticket:$id" "work-class-missing" "no work_class field: detention/capped/cost-cap could not scope — refused to run the unfiltered chain"
    bash "$FLEET/release.sh" "$id" >/dev/null 2>&1 || true; current=""
    bash "$FLEET/loop-guard.sh" record "$id" "$DROID" >/dev/null 2>&1 \
      || echo "[$DROID] LOOP-GUARD: $id quarantined (no work_class)." >&2
    continue
  fi
  pfile="$(awk -F': ' '$1=="prompt"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  spec="$(cat "$tfile"; echo; echo '--- WORK SPEC ---'; cat "$pfile" 2>/dev/null || echo '(no prompt file)')"
  branch="$(awk -F': ' '$1=="branch"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  # TICKET-MAP-GATE — CREATION-TIME work-lease enforcement. The commit-time hook already refuses a
  # worktree branch that maps to no board ticket, but it fires AFTER the build is finished (four
  # agents lost complete, green work to that late refusal in one day). Run the SAME resolver HERE,
  # before the worktree is created and before the model is launched, so an unmapped branch costs
  # nothing. Fail-closed and loud: a missing/blank `branch:` field or a branch that resolves to no
  # ticket RELEASES the claim instead of dispatching a build that could never be committed.
  if ! bash "$FLEET/work-lease.sh" guard-branch "$branch" "ticket $id"; then
    echo "[$DROID] $id: branch '$branch' maps to NO board ticket — REFUSING to create a worktree or launch a build for work that could not be committed. Fix the ticket's 'branch:' field. Releasing; next…" >&2
    bash "$FLEET/release.sh" "$id" || true; current=""; continue
  fi
  # MULTI-REPO: resolve the ticket's target repo (`repo:` field; absent -> charon product).
  # RR_PATH/RR_WT/RR_BASE/RR_GATE come from repo-registry.sh; owner/repo is derived (not hardwired).
  repokey="$(awk -F': ' '$1=="repo"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  if ! repo_resolve "$repokey" "$id"; then
    echo "[$DROID] $id names UNKNOWN repo '$repokey' (known: $(repo_known_keys)) — releasing; fix the ticket's repo: field." >&2
    bash "$FLEET/release.sh" "$id" || true; current=""; continue
  fi
  REPO="$RR_PATH"; wt="$RR_WT"; base_ref="origin/$RR_BASE"
  echo "[$DROID] $id -> repo=$RR_KEY ($REPO) base=$RR_BASE worktree=$wt"
  # MED-3: RE-STAMP the commit identity per ticket, now that the target repo is known. The
  # launch-time stamp is the droid id, which is right for the rig but would publish internal rig
  # taxonomy (tier name + pid, @fleet.local) into the PUBLIC product's history. One droid handles
  # tickets for several repos in a session, so this must be re-picked every iteration.
  droid_identity_for_repo "$RR_KEY" "$DROID" >/dev/null
  echo "[$DROID] $id commit stamp: $GIT_COMMITTER_NAME <$GIT_COMMITTER_EMAIL> (repo=$RR_KEY)"
  # #1 WORKTREE-LEAK GUARD (a): the LAUNCHER creates the worktree off the repo's base branch
  # BEFORE the model runs, so the create/cd step is out of the model's hands — a model that
  # ignores it can no longer land in the main checkout undetected. On failure we FAIL LOUDLY and
  # never launch into the main checkout. A live needs-push marker means committed-but-unlanded
  # work is sitting in that worktree — REFUSE to re-run (would risk destroying it); manager lands.
  npmark="$FLEET/state/needs-push/$id"
  mkdir -p "$(dirname "$wt")"
  # P0 #4 (DROID-LIFECYCLE-REAP): use the P0-guarded worktree setup so a pre-existing branch
  # with unmerged commits is REUSED, not `-B`-reset from origin/master. The upstream
  # `leak_worktree_setup` (in leak-guard.sh) is kept untouched (out of this ticket's owns);
  # this wrapper adds the fail-closed unique-commits check + REUSE path on top, and DELEGATES
  # to the upstream only when the branch provably has no unique commits (== safe to recreate).
  # The upstream's own refusal codes therefore still propagate through this wrapper and are
  # handled below — rc 3 (salvage-tagged unlanded commits) included.
  set +e; p0_worktree_setup "$REPO" "$wt" "$branch" "$npmark" "$base_ref"; lg_rc=$?; set -e
  if [ "$lg_rc" -eq 3 ]; then
    echo "[$DROID] $id: branch '$branch' has UNLANDED commits — leak-guard salvage-tagged them and REFUSED to recreate the worktree. Land or delete that branch by hand; NOT re-running. Next…" >&2
    current=""   # keep the claim marker so it isn't re-offered; a human decides
    continue
  elif [ "$lg_rc" -eq 2 ]; then
    echo "[$DROID] $id has committed-but-unlanded work (state/needs-push/$id) — NOT re-running (would risk its worktree). Land it: fleet/land-needs-push.sh $id. Keeping claim; next…" >&2
    current=""   # keep the claim marker so it isn't re-offered; manager lands it
    continue
  elif [ "$lg_rc" -ne 0 ]; then
    echo "[$DROID] FATAL: could not create worktree $wt off $base_ref — REFUSING to launch into the main checkout $REPO. Releasing $id for retry." >&2
    bash "$FLEET/release.sh" "$id" || true; current=""
    bash "$FLEET/loop-guard.sh" record "$id" "$DROID" \
      || echo "[$DROID] LOOP-GUARD: $id quarantined (repeated worktree-create failures)."
    continue
  fi
  # WORK-LEASE: claim.sh already acquired the atomic lease (state/claims/$id) at DISPATCH — that
  # is the double-claim gate. Now that the isolated worktree exists, BIND the lease to it so the
  # commit-time hook can verify the worktree match. Non-fatal (the claim IS the lease regardless).
  bash "$FLEET/work-lease.sh" bind "$id" "$wt" "$DROID" >/dev/null 2>&1 || true
  # Snapshot the main checkout so the post-session leak detector can spot NEW stray work in it.
  main_before="$(git -C "$REPO" status --porcelain 2>/dev/null)"
  # LAUNCHER NOTE wins over JOIN-PROMPT step 1: the worktree already exists and is the CWD.
  launcher_note="=== LAUNCHER NOTE (overrides step 1 of the join prompt) ===
Your isolated worktree ALREADY EXISTS and is your current working directory:
  $wt   (branch $branch, freshly created off $base_ref by the launcher)
Do NOT run 'git worktree add' or 'git worktree remove'. SKIP the worktree-creation step.
Verify you are in $wt (run: pwd), then begin at the implementation step. NEVER edit the main
checkout $REPO — only files under $wt.
"
  prompt="$launcher_note
$(cat "$FLEET/JOIN-PROMPT.md")

=== YOUR ASSIGNED TICKET: $id ===
$spec"
  # OFF-CLAUDE EXECUTION (the ONE step that changed): run the droid's work THROUGH THE GATEWAY via
  # the swappable client ($CHARON_AGENT_CMD), NOT `claude -p`. `claude -p` speaks the Anthropic
  # Messages API directly (no ANTHROPIC_BASE_URL) and burns Claude tokens; the gateway client routes
  # `charon/<model>` to 4-LOM (non-Claude models, cheapest-usage-first, roll-to-next-on-exhaust). The
  # prompt becomes the client's BRIEF FILE; the tier's gateway chain ($MODELS) drives cross-model
  # failover. The client cds into the worktree itself (its <cwd> arg). Success == exit 0 (charon-run.sh
  # returns 0 on a model success, non-zero when every model in the chain is exhausted).
  brief="$FLEET/state/agent-briefs/$DROID-$id.md"; mkdir -p "$(dirname "$brief")"
  printf '%s' "$prompt" > "$brief"
  outlog="$FLEET/state/agent-logs/$DROID-$id.txt"; mkdir -p "$(dirname "$outlog")"
  # CHARON_JOB_REF/CHARON_JOB_WORK_CLASS: env fallback the capture pipeline's
  # job-meta.sh reads (fleet/capture/job-meta.sh) so charon-run.sh's scorecard
  # capture hook can tag the ref/work_class without any new plumbing.
  if CHARON_JOB_REF="$id" CHARON_JOB_WORK_CLASS="$wclass" "$CHARON_AGENT_CMD" "$wt" "$outlog" "$brief" "${RUN_MODELS[@]}"; then
    # #1 WORKTREE-LEAK GUARD (b): did the droid leak into the main checkout instead of its worktree?
    # (0 commits AND clean worktree AND the main checkout gained NEW porcelain entries.)
    if [ "$(leak_detect "$REPO" "$wt" "$branch" "$main_before" "$base_ref")" = LEAK ]; then
      lf="$(leak_capture "$REPO" "$id" "$FLEET/state/leaks")"
      {
        echo ""
        echo "[$DROID] !!! LEAK DETECTED for $id !!! The droid wrote into the MAIN checkout"
        echo "[$DROID]     $REPO instead of its worktree (0 commits, clean worktree, main newly dirty)."
        echo "[$DROID]     Stray work CAPTURED (quarantined) -> $lf"
        echo "[$DROID]     Main checkout LEFT UNTOUCHED for manager recovery. NOT releasing/publishing $id."
        echo "[$DROID]     MANAGER: recover from the capture, clean $REPO, then 'fleet/release.sh $id'."
      } >&2
      current=""   # keep the claim so the ticket isn't re-run over the un-recovered leak
      continue
    fi
    # The droid committed its work on its branch but does NOT push or open the PR: the
    # deny-list blocks `git push`/`gh pr create` inside the Claude session (even with
    # --dangerously-skip-permissions, which does NOT bypass deny rules). So the LAUNCHER
    # publishes here in plain operator-shell — NOT a Claude Bash tool call — so the
    # deny-list never applies. Read <branch> from the ticket via the same awk meta pattern.
    branch="$(awk -F': ' '$1=="branch"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
    # wt / REPO / base_ref already resolved above from the ticket's repo: field (multi-repo).
    # SAFETY NET (FR1 root cause): a droid can exit 0 with work left UNCOMMITTED — it made the
    # edits but never ran `git commit`. Pushing then publishes an EMPTY branch (gh pr create
    # fails → NEEDS-PUSH) and strands the work in the worktree, where a later re-claim's
    # `git worktree remove --force` (JOIN-PROMPT) DESTROYS it. So auto-commit any leftover first:
    # the work is always captured and still goes through the PR/CI/review gate. The commit message
    # flags it so the manager scrutinizes for half-done work.
    if [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]; then
      echo "[$DROID] WARNING: $id left UNCOMMITTED changes — launcher auto-committing (droid exited without committing)."
      git -C "$wt" add -A
      git -C "$wt" commit -q -m "chore($id): launcher auto-commit — droid exited without committing (review for completeness)" || true
    fi
    # If there are STILL no commits beyond base, the droid produced nothing — a genuine no-op.
    # Release for retry rather than pushing an empty branch.
    # FAIL CLOSED (fix #1, third call site of the same shape). An empty `git log` here also
    # meant "no commits", including when it was empty because $base_ref did not resolve — which
    # released the claim and declared the droid a no-op while its commits sat on the branch.
    # Fetch first (fix #2) so $base_ref is actually resolvable, then demand a NUMERIC zero.
    git -C "$wt" fetch origin --quiet 2>/dev/null || true
    nc="$(_lg_unlanded_count "$wt" "$branch" "$base_ref")" || nc=""
    case "$nc" in ''|*[!0-9]*) nc="" ;; esac
    if [ -z "$nc" ]; then
      echo "[$DROID] WARNING: cannot resolve '$base_ref' in $wt — refusing to declare $id a no-op; treating it as having work and continuing to the push/submit path." >&2
    fi
    if [ -n "$nc" ] && [ "$nc" -eq 0 ]; then
      echo "[$DROID] $id produced NO commits and NO changes — releasing for retry (nothing to publish)."
      bash "$FLEET/release.sh" "$id" || true; current=""
      # LOOP-GUARD: count this zero-commit release. After N (default 2) of the SAME id in this
      # run, loop-guard.sh quarantines it (claim.sh then skips it) so we can't spin forever on
      # a parked/blocked/bad-prompt ticket and starve the next ready one. It prints the
      # escalation itself and exits 2 on quarantine.
      bash "$FLEET/loop-guard.sh" record "$id" "$DROID" \
        || echo "[$DROID] LOOP-GUARD: $id quarantined for this board — skipping it from now on."
      continue
    fi
    # Drop any stale remote branch from a prior/closed PR so the push fast-forwards, then
    # push + open the DRAFT PR. If either fails, fall through: submit.sh grounds on a real
    # open PR and flags state/needs-push when there isn't one. `|| true` keeps set -e happy.
    git -C "$wt" push origin --delete "$branch" 2>/dev/null || true
    # Title from the commit subject, NOT `--fill`: the worktree has no local base
    # ref, so `--fill` (which computes `base...branch`) fails and no PR opens. A
    # commit-subject title needs no base ref and is robust.
    pr_title="$(git -C "$wt" log -1 --pretty=%s 2>/dev/null || echo "$id")"
    # MULTI-REPO: PR target owner/repo is DERIVED from the ticket's repo (not hardwired to
    # SLOP-Platform/charon); base is the repo's base branch (master for charon, main for keystone).
    owner_repo="$(repo_owner_repo "$REPO")"
    # SESSION-REPORT-WIRE: derive the gate's REAL exit code BEFORE pushing, so the report's
    # GATE field is grounded in the launcher's own observation — never the model's self-report.
    # The model already ran the gate during its session; the launcher's run is the verification
    # the wire needs to make `GATE: PASS` mean something. Cost is bounded: the worktree is on
    # disk, the diff is final, the suite is the same one. A green re-run is incremental.
    #
    # Skipped under --push-only / bridge-managed dispatches when a `skip-launcher-gate` marker
    # file is present (operator escape hatch — same env var land-push.sh honors); absent the
    # marker, the gate runs unconditionally and its exit code is what the report records.
    GATE_EXIT=1   # default to FAIL so a crash / skip reads as FAIL not PASS
    if [ -e "$FLEET/state/skip-launcher-gate/$id" ]; then
      echo "[$DROID] $id: skip-launcher-gate marker present — launcher skips its gate run, recording GATE=NOT-RUN in the report (operator escape hatch)." >&2
      GATE_EXIT=125  # distinct sentinel: 125 == "launcher did not run the gate"
    else
      echo "[$DROID] $id: launcher running the gate (one-shot verification)..."
      # ORDERING + set -e (2026-08-01): this block had TWO ways to kill the WHOLE TAB, and
      # `GATE_EXIT=$?` was unreachable on any failure — so the FAIL default and the 125
      # sentinel above were dead code for exactly the path they exist to describe.
      #   1. the mkdir ran AFTER the redirect. bash opens the target when it sets up the
      #      redirection, so a missing dir fails the command outright -> `set -e` exits the tab.
      #   2. a RED gate is a non-zero compound command in plain statement position, so
      #      `set -e` exits the tab there too. Measured: `( false ) > f; RC=$?` never reaches
      #      the assignment. A failing gate must be DATA (an exit code we record), not a fault.
      # Both are why pools drained below their floor and tickets fell back to READY holding a
      # claim: the tab died mid-ticket instead of recording a FAIL and moving on.
      # mkdir is NOT `|| true`: if the results dir cannot be created the redirect below WILL
      # fail, and silently swallowing that just moves the tab-kill one line down. Fail here,
      # loudly, with the reason — but as DATA (a recorded FAIL), not an unwind.
      if ! mkdir -p "$FLEET/state/gate-results" 2>/dev/null; then
        echo "[$DROID] $id: cannot create $FLEET/state/gate-results — recording gate FAIL (exit 126)" >&2
        GATE_EXIT=126
      else
        gate_log="$FLEET/state/gate-results/$DROID-$id.txt"
        # `|| GATE_EXIT=$?` instead of toggling `set +e`/`set -e` around the call. A command on
        # the left of `||` is in a CONDITION context, where `set -e` does not fire at all — so
        # the failing gate is captured as data without ever mutating global shell options.
        # Toggling would also re-enable `set -e` UNCONDITIONALLY, which is correct here only by
        # coincidence (this script sets it at :17) and silently wrong if that ever changes.
        # (Raised by adversarial review of PR #356.)
        GATE_EXIT=0
        ( cd "$wt" && eval "$RR_GATE" ) > "$gate_log" 2>&1 || GATE_EXIT=$?
      fi
      echo "[$DROID] $id: launcher gate exit code = $GATE_EXIT"
      # $gate_log had NO reader anywhere in the rig (grep -rn gate-results = these lines only),
      # so a RED gate discarded its own diagnosis and the skipped publish downstream looked
      # causeless. Surface the tail on failure — silent report loss is the defect, not the log.
      # `${gate_log:-}` and the -r test, NOT a bare "$gate_log": under `set -u` the mkdir-failed
      # branch above leaves gate_log UNSET, and referencing it bare would abort the tab here —
      # re-introducing the exact class this block fixes, one line further down.
      if [ "$GATE_EXIT" -ne 0 ]; then
        if [ -r "${gate_log:-}" ]; then
          echo "[$DROID] $id: gate FAILED (exit $GATE_EXIT) — last 40 lines of $gate_log:" >&2
          # `>&2` BEFORE `2>/dev/null`: redirections apply left to right, so the reverse order
          # points stdout at an already-nulled stderr and silently swallows the diagnosis.
          tail -40 "$gate_log" >&2 2>/dev/null || true
        else
          echo "[$DROID] $id: gate FAILED (exit $GATE_EXIT) — no readable gate log at '${gate_log:-<unset>}'" >&2
        fi
      fi
    fi
    # Capture the model's CHARON_RUN_RESULT for the SESSION line (already on disk in the outlog).
    CHARON_RUN_RESULT=""
    [ -r "$outlog" ] && CHARON_RUN_RESULT="$(grep -E '^CHARON_RUN_RESULT=' "$outlog" 2>/dev/null | tail -1 | sed 's/^CHARON_RUN_RESULT=//')"
    : "${CHARON_RUN_RESULT:=UNKNOWN — outlog missing or unparseable}"
    # Render the full v1 block (derived + judgment + any self-report). $owns_list comes from the
    # ticket's owns: field (re-read at submit time so a field change since claim is honored).
    owns_list="$(awk -F': ' '$1=="owns"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
    report_block="$(emit_session_report "$id" "$DROID" "$branch" "$wt" "$REPO" \
                       "$base_ref" "${RUN_MODELS[0]:-}" "$CHARON_RUN_RESULT" \
                       "$GATE_EXIT" "$owns_list" "DONE" "$outlog")"
    # Echo to the operator's tab so it's visible without needing the file.
    echo "[$DROID] $id session report:"; printf '%s\n' "$report_block"
    git -C "$wt" push -u origin "$branch" \
      && gh pr create --repo "$owner_repo" --base "$RR_BASE" --head "$branch" --draft \
           --title "$pr_title" \
           --body "Automated draft PR for $id. See the commit and docs/review-log/$id.md.

Draft is the launcher default — NOT a hold signal. A real hold is the \`hold\` label + a \`HOLD:\` comment.

---

$report_block" \
      || true
    if bash "$FLEET/submit.sh" "$id"; then
      current=""; echo "[$DROID] $id submitted (PR open). Next…"
    else
      # submit refused: work committed but no real PR (push or gh-pr-create failed). Keep the
      # claim + worktree (don't let another droid redo it); submit flagged state/needs-push
      # for the manager to land.
      current=""; echo "[$DROID] $id: work committed but NO PR opened — flagged needs-push; manager lands it. Next…"
    fi
  else
    bash "$FLEET/release.sh" "$id" || true; current=""
    # LOOP-GUARD: a non-zero exit is also a zero-commit release — count it so repeated
    # hard failures on the SAME id are quarantined rather than re-claimed forever.
    bash "$FLEET/loop-guard.sh" record "$id" "$DROID" \
      || echo "[$DROID] LOOP-GUARD: $id quarantined for this board (repeated non-zero exits) — skipping it from now on."
    echo "[$DROID] $id session exited non-zero — released for retry."
    # SESSION-REPORT-WIRE: a session that REFUSED via non-zero exit is "the most valuable report
    # of all" per the v1 format spec. Write the report with STATUS=BLOCKED and GATE=NOT-RUN so the
    # manager sees what happened without needing to dig into the agent log.
    CHARON_RUN_RESULT=""; [ -r "${outlog:-}" ] && CHARON_RUN_RESULT="$(grep -E '^CHARON_RUN_RESULT=' "${outlog:-}" 2>/dev/null | tail -1 | sed 's/^CHARON_RUN_RESULT=//')"
    : "${CHARON_RUN_RESULT:=UNKNOWN — outlog missing or unparseable}"
    owns_list="$(awk -F': ' '$1=="owns"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
    if [ -n "$outlog" ] && [ -r "$outlog" ]; then
      emit_session_report "$id" "$DROID" "$branch" "$wt" "$REPO" \
        "$base_ref" "${RUN_MODELS[0]:-}" "$CHARON_RUN_RESULT" \
        "125" "$owns_list" "BLOCKED" "$outlog" >/dev/null || true
    else
      echo "[$DROID] $id: no outlog on a non-zero exit — skipping report (no transcript to derive from)." >&2
    fi
  fi
done
