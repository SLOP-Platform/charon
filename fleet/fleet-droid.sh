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
usage(){ echo "usage: fleet-droid.sh <frontier|strong|economy|low|med|high|opus|sonnet|haiku> [--wait <min>] [--retries <n>] [--patience <cycles>] [--serial-justified=<reason>] [--only <TICKET-ID>]"; exit 2; }

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
# Prints the surviving comma chain on stdout; returns 7 when EVERY model is capped (tier exhausted
# -> caller SPILLS UP). Fail-OPEN: if the gateway is unreachable / status unavailable, every model
# reads 'unknown' and is KEPT (rc 0) — we never escalate to a paid tier merely because the status
# endpoint is down. Reuses the capability/availability.py `filter-capped` CLI (ONE snapshot read).
capped_filter_chain(){
  local py="$FLEET/capability/availability.py"
  { [ -f "$py" ] && command -v python3 >/dev/null 2>&1; } || { ( IFS=','; echo "$*" ); return 0; }
  local out rc
  set +e; out="$(python3 "$py" filter-capped "$@" 2>/dev/null)"; rc=$?; set -e
  [ "$rc" -eq 7 ] && return 7                       # positively ALL-capped -> exhausted
  [ "$rc" -ne 0 ] && { ( IFS=','; echo "$*" ); return 0; }   # any other error -> fail-open keep all
  local kept=() m
  while IFS= read -r m; do [ -n "$m" ] && kept+=("$m"); done <<<"$out"
  [ "${#kept[@]}" -gt 0 ] || { ( IFS=','; echo "$*" ); return 0; }
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
        if capf="$(capped_filter_chain "${dmodels[@]}")"; then
          [ -n "$spilled" ] && echo "[fleet-droid] SPILL-UP: cost band '$start' had NO runnable model (all detained/capped); escalated to '$cur' (cost ceiling '$ceiling') — a paid model does the work rather than backlogging for cheap." >&2
          echo "$capf"; return 0
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
  rtier="${2:?resolve needs: <tier> <ticketfile>}"; rtfile="${3:?resolve needs: <tier> <ticketfile>}"
  [ -f "$rtfile" ] || { echo "[fleet-droid] resolve: no such ticket file: $rtfile" >&2; exit 2; }
  rcanon="$(canon_tier "$rtier")"
  rline="$(tier_chain "$rcanon")"
  [ -n "$rline" ] || { echo "[fleet-droid] resolve: no gateway model chain for tier '$rtier' (canonical '$rcanon')." >&2; exit 3; }
  rwc="$(awk -F': ' '$1=="work_class"{sub(/^[^:]*: ?/,"");print;exit}' "$rtfile")"
  if [ -z "$rwc" ]; then
    echo "[fleet-droid] resolve: ticket $rtfile has no work_class — detention filter cannot scope; emitting FULL chain." >&2
    IFS=',' read -r -a RMODELS <<<"$rline" || true
    ( IFS=','; echo "${RMODELS[*]}" ); exit 0
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
trap 'cleanup; echo "[$DROID] stood down."; exit 130' INT TERM
trap cleanup EXIT
wmsg=""; [ "$WAIT_MIN" -gt 0 ] && wmsg=", wait=${WAIT_MIN}m retries=${RETRIES} patience=${PATIENCE}"
echo "[$DROID] charon-fleet droid up (off-Claude via ${CHARON_AGENT_CMD##*/}; gateway chain=${MODELS[*]}$wmsg). Ctrl-C to stand down."
while true; do
  # Tier patience: try OWN tier first; only dip to lower tiers once we've been
  # empty-at-own-tier for >= PATIENCE wait-cycles (gives lower tiers a head start).
  mode=both; [ "$empties" -lt "$PATIENCE" ] && mode=own-only
  if ! res="$(bash "$FLEET/claim.sh" "$TIER" "$DROID" "$mode")"; then
    if [ "$WAIT_MIN" -gt 0 ] && { [ "$RETRIES" -eq 0 ] || [ "$empties" -lt "$RETRIES" ]; }; then
      empties=$((empties+1))
      rmax="$RETRIES"; [ "$RETRIES" -eq 0 ] && rmax="∞"
      echo "[$DROID] no $TIER-eligible work — waiting ${WAIT_MIN}m (empty $empties/$rmax)…"
      sleep "$((WAIT_MIN*60))"; continue
    fi
    echo "[$DROID] no $TIER-eligible work left — standing down."; break
  fi
  empties=0
  read -r _tag id tfile <<<"$res"; current="$id"
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
    echo "[$DROID] WARNING: $id has no work_class field — detention/capped filter cannot scope; running the FULL chain unfiltered." >&2
    RUN_MODELS=("${MODELS[@]}")
  fi
  pfile="$(awk -F': ' '$1=="prompt"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  spec="$(cat "$tfile"; echo; echo '--- WORK SPEC ---'; cat "$pfile" 2>/dev/null || echo '(no prompt file)')"
  branch="$(awk -F': ' '$1=="branch"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
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
    git -C "$wt" push -u origin "$branch" \
      && gh pr create --repo "$owner_repo" --base "$RR_BASE" --head "$branch" --draft \
           --title "$pr_title" \
           --body "Automated draft PR for $id. See the commit and docs/review-log/$id.md.

Draft is the launcher default — NOT a hold signal. A real hold is the \`hold\` label + a \`HOLD:\` comment." \
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
  fi
done
