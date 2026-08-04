#!/usr/bin/env bash
# rig-ci-scope.sh — the DIFF-SCOPING BRAIN of the rig's CI gate (.github/workflows/rig-ci.yml).
#
# WHY THIS FILE EXISTS (do not fold it back into validate_board.sh):
#   fleet/validate_board.sh is only board-accurate in the LIVE tree. `fleet/state/` is gitignored,
#   so a CI checkout has NO done-markers: every already-done ticket reads as LIVE and the validator
#   emits FALSE REDs on a clean PR. A gate that reds on a clean tree gets disabled or bypassed —
#   i.e. a gate that stops actually running [[gates-must-actually-run]].
#   So CI does NOT run validate_board.sh. It runs the MARKER-INDEPENDENT subset, below, scoped to
#   the ticket files CHANGED IN THE PR.
#   validate_board.sh is ALSO contended by four live tickets (REPO-MAP-CONVERGE, REPO-FIELD-REQUIRED,
#   CREATION-GATE-DECOMPOSE-WIRE, PROJECT-MEMBERSHIP-GATE) — this script must never become a fifth
#   writer of it. If validate_board.sh ever needs a real fresh-checkout flag, that is a SEPARATE
#   ticket sequenced behind those four.
#
# IN SCOPE (marker-independent — answerable from the ticket file alone):
#   field presence (branch, owns), work_class present + enum-valid, repo: valid when present,
#   D&S section present, owns-format.
# OUT OF SCOPE, DELIBERATELY (marker-DEPENDENT — unanswerable in a fresh checkout):
#   live-vs-done status, retirement/archive state, dependency satisfaction, done-marker orphans,
#   owns-collision between live tickets. Those belong to the LIVE preflight, never to CI.
#
# REENTRANCY [[fleet-selfcheck-forkbomb-class]]: this script must NEVER invoke preflight.sh,
# validate_board.sh, gh, or anything that re-triggers CI. It is pure local file inspection + git diff.
#
# Usage:
#   rig-ci-scope.sh changed            list PR-changed files (informational)
#   rig-ci-scope.sh syntax             `bash -n` every CHANGED *.sh  -> rc!=0 on any syntax break
#   rig-ci-scope.sh shellcheck         whole-tree shellcheck BASELINE RATCHET (see cmd_shellcheck
#                                       below) -> rc!=0 on any NEW (file, SC-code) finding
#   rig-ci-scope.sh board              marker-independent validation of CHANGED fleet/board/*.md
#   rig-ci-scope.sh suites             print the CI test ALLOWLIST, one per line
#   rig-ci-scope.sh tests              run the allowlisted suites -> rc!=0 on any failure
# Env:
#   RIG_CI_BASE  base ref/sha for the diff (default: origin/master)
#   RIG_CI_HEAD  head ref/sha for the diff (default: HEAD)
#   RIG_CI_ROOT  repo root to operate on   (default: this script's repo)
# Exit: 0 = GREEN, 1 = RED (a real failure), 2 = usage.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${RIG_CI_ROOT:-$(cd "$HERE/../.." && pwd)}"
BASE="${RIG_CI_BASE:-origin/master}"
HEAD_REF="${RIG_CI_HEAD:-HEAD}"

# ---- CI TEST ALLOWLIST (ALLOWLIST, NOT AN EXCLUDE-LIST) -------------------------------------
# fleet/tests/ contains BENCHMARK GRADER suites that invoke real models over the network and can
# block for HOURS. CI therefore names its suites LITERALLY: anything added to fleet/tests/ later is
# excluded BY DEFAULT and only runs in CI once someone deliberately adds it here after proving it
# is hermetic, offline and fast. NEVER replace this with a `for t in fleet/tests/*.test.sh` sweep.
CI_SUITES=(
  priority-validator.test.sh # hermetic: throwaway fleet + synthetic board under mktemp -d, no
                            # network. Red-proofs the canonical numeric priority axis: drift
                            # surface rejects HIGH/MEDIUM/P2/non-integer values; ladder surface
                            # exercises priority>blocking>blast>difficulty>id end-to-end through
                            # the real claim.sh. The single canary a revert to "alphabetical
                            # first" or a drop of the revdep field fails. ~2s.
  rig-ci.test.sh            # this gate's own fail-on-revert tests
  board-file-ratchet.test.sh # hermetic merge-result guard against board ticket drops
  tier-drift.test.sh        # hermetic: isolated temp fleets under mktemp -d (own

                            # validate_board.sh + capability/ + checks/ + a 2-ticket board
                            # copied from the real one), no network, ~1s. Red-proofs the
                            # validate_board "2f" TIER-DRIFT gate on every path it shipped
                            # broken: the RED-set file is present AND git-tracked (without it
                            # the gate cannot go RED in any configuration), a mis-tiered
                            # security ticket drives rc 3 -> RED preflight end to end, a
                            # MISSING or rc-2-exiting classifier is RED instead of silently
                            # green (fail-closed), a zero-item scan is RED not a confident
                            # pass, and SEC_RE stays anchored so d1 docs are not routed to
                            # the most expensive frontier chain.
  work-lease.test.sh        # hermetic: real work-lease.sh/claim.sh/_lib.sh copied into a temp
                            # FLEET + REAL git worktrees under mktemp -d, no network. Red-proofs
                            # the DISPATCH double-claim gate, the single (claims) store shared
                            # with claim.sh, the un-leased / main-checkout / fail-closed commit
                            # refusals, and stale-lease reclaim. ~2s.
  substrate-first-gate.test.sh # hermetic: throwaway board + fixture EVAL-REGISTRY under mktemp -d,
                            # no network. Red-proofs the creation-time build-vs-adopt gate on all
                            # its detection paths (requirement / anti-reframe diagnostic /
                            # registry-alignment consult / same-change provenance). ~1s.
  rule-coverage.test.sh     # hermetic: throwaway RULE_COVERAGE_* fixtures under mktemp -d, no
                            # network. Red-proofs the §11 coverage meta-gate on every branch
                            # (all-covered GREEN, un-exempted mechanizable GAP RED, fake-green
                            # nonexistent/unwired artifact RED, expired exemption RED, phantom
                            # doc_anchor RED, completeness floor RED). ~1s.
  base-integrity.test.sh    # hermetic: isolated git fixture, BASE_INTEGRITY_OFFLINE
  board-correctness.test.sh # hermetic: throwaway board fixture
  parked-semantics.test.sh  # hermetic
  log-prune.test.sh         # hermetic
  land-push-ci-gate.test.sh # hermetic: throwaway bare remote + gh STUB, no network, ~2s
  land-safety.test.sh       # hermetic: throwaway bare remotes under mktemp -d; origin is a
                            # FILESYSTEM path, so land-push's CI gate short-circuits at the
                            # "origin is not a github.com remote" branch — gh is never invoked
                            # and nothing leaves the box. ~1s. This is the ONLY suite defending
                            # the stale-bare-name guard, i.e. the very defect (report success
                            # while publishing NOTHING) this script exists to prevent; it was
                            # unenforced in CI until 2026-07-19.
sync-checkouts.test.sh    # hermetic: mktemp git fixtures + a fixture fleet dir. Defends the
                            # SESSION-START path — no silent branch flip, bounded fetches, and
                            # the only test that actually EXECUTES preflight.sh's `scan` dispatch
                            # (every other preflight test sources the file, which the BASH_SOURCE
                            # guard makes skip the dispatch entirely). Its one network case dials
                            # RFC 5737 TEST-NET-1, which is unroutable by definition, under a 3s
                            # timeout — nothing leaves the box. ~20s.
  stranded-work.test.sh     # hermetic: real git repos + a real local BARE remote under mktemp -d;
                            # PR state is injected as a TSV fixture (SW_PR_FIXTURE), so `gh` is
                            # never invoked and nothing leaves the box. ~2s. Guards the recurring
                            # stranded-work detector, including its never-report-clean-when-
                            # undetermined contract.
  flow-canary.test.sh       # hermetic: a local Python stdlib HTTP fake gateway on 127.0.0.1 stands
                            # in for the LIVE gateway (serves /charon/status + /v1/chat/completions);
                            # the REAL fleet/flow-canary.sh runs against it via env overrides. No
                            # live network. Fail-on-revert dogfood: seeds a mis-route / free-first
                            # violation / inert meter (#167) / parked-served + parked-attempted
                            # (#188) / stray-`standard` tier / unserved head model, and proves the
                            # canary goes RED on each then GREEN on revert. ~5s.
  verify-restart-cmds.test.sh # hermetic: fixture registries + fixture scripts under mktemp -d,
                            # VERIFY_UNITS_DIR pinned to an empty temp dir, and a STUB verify for
                            # the monit-selfwatch cases (SELFWATCH_VERIFY). No network, no sudo, no
                            # monit, nothing installed. Its one real-file touch is a text-only
                            # --static-only pass over the committed service-registry.tsv. Guards
                            # the monit PRE-ENABLE gate: re-seeds all four original broken
                            # restart_cmds (missing systemd unit / `systemctl --user` as root /
                            # relative path with cwd=/ / ~/.ssh Host alias + remote sudo) and
                            # proves verify REDs on each, that a zero-row or malformed registry is
                            # never a silent pass, and that the `enable --now monit` line is not
                            # even PRINTED while verify is RED. ~2s.
  fixture-bypass.test.sh    # hermetic: synthetic trees under mktemp -d only; no network, no gh,
                            # no git writes, no fleet/state/ dependency. ~2s. Guards the
                            # "green over a production path no test ever runs" class — six
                            # confirmed instances on 2026-07-19. Its deep (mutation) mode is
                            # reentrancy-guarded and is NOT exercised against any rig suite here;
                            # the suite mutates only its own throwaway fixtures.
  status-board.test.sh      # hermetic: every source of fleet/status-board/generate.sh is env-
                            # overridden to a printf stub or a mktemp -d fixture, and the two
                            # NETWORK sources use their documented offline hooks (SB_PR_FIXTURE,
                            # SB_GATEWAY_{STATUS,CONFIG}_JSON) — no gh, no curl, no gateway, no git
                            # remote. ~5s. Red-proofs the operator-facing status page's ONE
                            # contract: three states, never two. Five reverts were each VERIFIED to
                            # drive it RED — _verdict going unconditionally green (the tile-sized
                            # version of the 114-unenforced-proof lie), _proof failing OPEN on an
                            # unreadable allowlist, and _run's not-found / timed-out / printed-
                            # nothing refusals. It also carries the POSITIVE control (a working,
                            # CI-enforced source really does render PASSING), so the page cannot
                            # satisfy the suite by greying everything out either. A page that
                            # renders an unknown as green is worse than no page, which is exactly
                            # why this suite is in CI and not merely written.
  gate-integrity.test.sh    # hermetic: synthetic gate trees under mktemp -d only; no network, no
                            # gh, no git writes, no fleet/state/ dependency. ~2s. Guards THE GATE
                            # ON THE GATES — the "reads as protection, provides none" class
                            # (inert gate, false wiring claim, un-allowlisted proof suite). Its
                            # own gate is reentrancy-guarded and executes no suite, so putting
                            # this suite in CI cannot recurse.
  shellcheck-ratchet.test.sh # hermetic: throwaway mktemp -d *.sh fixtures, real shellcheck
                            # invocations (no network, no git writes, no fleet/state/ dependency).
                            # <1s. Red-proofs fleet/checks/shellcheck-ratchet.sh: a baselined
                            # finding count doesn't RED, a NEW instance (or a finding in a
                            # brand-new file) does, a missing baseline fails CLOSED (rc 2, not a
                            # silent pass), fixing a finding never re-REDs, and — the revert proof
                            # — the SAME clean fixture REDs under bare `shellcheck -o all` with no
                            # ratchet, which is exactly what unconditional enablement would have
                            # done to every PR (~36,700 pre-existing findings, automatic reject).
)

VALID_WORK_CLASSES="bugfix ci-infra design-review docs frontend generalist greenfield-feature money-path refactor rig-meta routing tests"
VALID_REPOS="charon product keystone ksf charon-private rig fleet"

RED=0
red(){ RED=1; echo "RED: $*"; }
info(){ echo "     $*"; }

# ---- diff scoping ----------------------------------------------------------------------------
# THE load-bearing line of this gate: CI inspects ONLY what the PR touched. Widening this to the
# whole tree re-introduces the false-RED class the fresh-checkout constraint exists to prevent
# (see fleet/tests/rig-ci.test.sh test 3, which reverts exactly this).
# FAIL CLOSED. `_merge_base` used to `|| echo "$BASE"` — falling back to the LITERAL ref string
# when the ref would not resolve. `git diff <literal> <head>` then failed to /dev/null, the changed
# list came back EMPTY, and cmd_board printed "board: 0 changed ticket(s) checked" with rc=0: a
# GREEN RECEIPT FOR HAVING CHECKED NOTHING. That is the vacuous-green class, the worst gate defect
# on this rig — uncertainty must never resolve to green.
#
# It reproduced ONLY in CI because rig-ci.yml exported RIG_CI_BASE/RIG_CI_HEAD as JOB-LEVEL env, so
# the `tests` step inherited them and the github.sha in RIG_CI_HEAD leaked into the throwaway
# fixture repos the suites build — where that sha does not exist. Locally those vars are unset, the
# refs resolve, and the defect stays invisible. Both ends are now fixed: the workflow scopes the
# vars to the steps that need them, AND this function refuses rather than guessing.
#
# _resolve_scope prints "<merge-base-sha> <head-sha>" and returns 0, or prints a reason to stderr
# and returns 1. EVERY caller must propagate that non-zero as a RED.
_resolve_scope(){
  local b h mb
  if ! h="$(git -C "$ROOT" rev-parse --verify -q "${HEAD_REF}^{commit}" 2>/dev/null)"; then
    echo "RED: diff HEAD '$HEAD_REF' does not resolve to a commit in $ROOT (RIG_CI_HEAD)." >&2
    echo "     Refusing: without a resolvable head the diff is empty and this gate would report" >&2
    echo "     a GREEN receipt for having checked nothing." >&2
    return 1
  fi
  if ! b="$(git -C "$ROOT" rev-parse --verify -q "${BASE}^{commit}" 2>/dev/null)"; then
    echo "RED: no resolvable diff base — '$BASE' is not a commit in $ROOT (RIG_CI_BASE)." >&2
    echo "     Refusing: without a resolvable base the diff is empty and this gate would report" >&2
    echo "     a GREEN receipt for having checked nothing. Fetch the base ref and rerun." >&2
    return 1
  fi
  if ! mb="$(git -C "$ROOT" merge-base "$b" "$h" 2>/dev/null)" || [ -z "$mb" ]; then
    echo "RED: '$BASE' and '$HEAD_REF' have no merge base in $ROOT (unrelated histories, or a" >&2
    echo "     shallow clone missing the common ancestor — check actions/checkout fetch-depth)." >&2
    echo "     Refusing rather than diffing against nothing and reporting a vacuous GREEN." >&2
    return 1
  fi
  printf '%s %s\n' "$mb" "$h"
}

# Prints the changed-file list. Returns non-zero if the scope could not be computed AT ALL —
# which is NOT the same as "the diff legitimately contains no matching files".
_changed_files(){
  local scope
  scope="$(_resolve_scope)" || return 1
  # shellcheck disable=SC2086  # $scope is deliberately word-split: "<base-sha> <head-sha>".
  git -C "$ROOT" diff --name-only --diff-filter=ACMR ${scope} --
}

# Process substitution (`< <(...)`) DISCARDS exit status, so a scope failure inside the loop feed
# would be silently read as "no files" — the vacuous green all over again. Every command that
# consumes the diff must therefore call this FIRST, before the loop, and return non-zero on refusal.
_require_scope(){
  _resolve_scope >/dev/null || { RED=1; return 1; }
  return 0
}

# Board files this run is responsible for. DIFF-SCOPED (see above).
_scoped_board_files(){
  _changed_files | grep -E '^fleet/board/[^/]+\.md$' || true
}

_scoped_sh_files(){
  _changed_files | grep -E '\.sh$' || true
}

# ---- checks ----------------------------------------------------------------------------------
# Informational, but it must not print an empty list and exit 0 when the scope is unresolvable —
# that is the same false receipt in miniature.
cmd_changed(){ _changed_files || RED=1; return $RED; }

cmd_syntax(){
  local n=0 f
  _require_scope || return $RED
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -f "$ROOT/$f" ] || continue          # deleted/renamed-away: nothing to parse
    n=$((n+1))
    if ! bash -n "$ROOT/$f" 2>&1; then
      red "shell-syntax: $f fails \`bash -n\`"
    else
      info "ok  $f"
    fi
  done < <(_scoped_sh_files)
  echo "shell-syntax: $n changed *.sh checked"
  return $RED
}

# The SHELLCHECK RATCHET (ticket SHELLCHECK-RATCHET, 2026-08-03). Whole-tree, not diff-scoped — unlike
# syntax/board this is not about fresh-checkout marker-independence, it is a debt ratchet: the
# committed fleet/checks/shellcheck-baseline.tsv is the accepted FLOOR (current findings at FULL
# coverage, `-o all` = default severities + all 11 optional checks, all off anywhere in this rig
# before this ticket — TOOL-UTILIZATION-AUDIT.md, 2026-08-01). Only a (file, SC-code) pair whose
# count EXCEEDS its baselined count REDs, so this can run over the whole tree every PR (~27s
# measured) without the ~36,700-finding bare-enablement automatic-reject. Mechanism lives in
# fleet/checks/shellcheck-ratchet.sh (hermetically tested by
# fleet/tests/shellcheck-ratchet.test.sh, allowlisted in CI_SUITES below) — this is a thin call-through
# so the rule cannot drift between this CI entry point and its test.
cmd_shellcheck(){
  bash "$HERE/shellcheck-ratchet.sh" check
  [ $? -eq 0 ] || RED=1
  return $RED
}

cmd_board(){
  local n=0 g=0 f t
  # Refuse BEFORE the loop. n=0 must mean "the diff genuinely carried no ticket files", never
  # "I could not compute the diff at all" — those two are indistinguishable in the output line.
  _require_scope || return $RED
  # Resolve the diff base ONCE for the grandfathering comparison (see _ticket_grandfathered).
  # Empty is FAIL-CLOSED there: every ticket is checked, i.e. exactly today's behaviour.
  _SCOPE_BASE="$(_resolve_scope 2>/dev/null | awk '{print $1}')"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -f "$ROOT/$f" ] || continue
    t="$(basename "$f" .md)"
    if _ticket_grandfathered "$f" "$ROOT/$f"; then
      g=$((g+1))
      info "skip $t (grandfathered — this PR changed no substrate-relevant field; formatting/data-only edit)"
      continue
    fi
    n=$((n+1))
    _check_ticket "$ROOT/$f" "$t"
  done < <(_scoped_board_files)
  # The diff WAS computed (guarded above), so n=0 here is a real, trustworthy "nothing to check".
  echo "board: $n changed ticket(s) checked, $g grandfathered (marker-independent checks only; diff scope resolved)"

  # n=0 used to be a clean GREEN even when the PR was 900 lines of new code, because the substrate
  # gate only ever saw fleet/board/*.md files. "Land code with no ticket" was therefore the cheapest
  # way to skip the gate entirely — it simply never ran. ONE call for the whole diff (not per-ticket):
  # a code change with no fleet/board/*.md ticket is a change the substrate question was never asked
  # about [[adopt-substrate-build-only-novel-slice]]. Not a duplicate of WORK-GATE-UNIVERSAL, which
  # specs decompose-sizing at launch and inert-code detection at done — neither asserts a code change
  # HAS a ticket. No-op (rc 0, "not applicable") when no diff range is resolvable.
  local _pht_out
  _pht_out="$(bash "$HERE/substrate-first-gate.sh" pr-has-ticket 2>&1)"
  if [ $? -ne 0 ]; then
    while IFS= read -r _l; do [ -n "$_l" ] && red "${_l#  RED  }"; done <<<"$_pht_out"
  else
    printf '%s\n' "$_pht_out"
  fi
  return $RED
}

_field(){ sed -n "s/^$2:[[:space:]]*//p" "$1" | head -1; }

_is_parked(){
  # Mirrors claim.sh / validate_board.sh: `parked: true` OR a note containing PARKED.
  local p; p="$(_field "$1" parked | tr 'A-Z' 'a-z')"
  case "$p" in true|yes|1) return 0;; esac
  grep -qi '^note:' "$1" && grep -q 'PARKED' "$1" && return 0
  return 1
}

# ---- GRANDFATHERING SCOPE: SEMANTIC, NOT BYTE ------------------------------------------------
# THE DEFECT THIS CLOSES (measured 2026-08-01): the per-ticket checks were scoped to "this file
# appears in the diff", which conflates two different things —
#     (1) this ticket's WORK changed        -> it must justify substrate, D&S, owns-format;
#     (2) this ticket's FILE was touched    -> may be a pure syntax/format repair.
# Under (2) a meaning-preserving YAML fix re-opens years of accumulated debt on unrelated tickets.
# Concretely: repairing 23 tickets whose frontmatter did not parse (the fail-open in
# substrate_first_gate.base_board_owns, PR #365) put them in a diff for the first time since they
# were written, and 21 pre-existing REDs fired — 13 of them "no 'substrate:' field". The gate made
# the repair of a gate defect UNLANDABLE. That is the gate-hardening-strands-work class, and it is
# exactly how `--force` habits start.
#
# THE RULE: a ticket ALREADY PRESENT on the base ref keeps its grandfathered status when none of
# the fields the verdict DEPENDS ON changed. If every input to a check is identical, the check can
# only reach the identical verdict — so re-running it discovers nothing new and blocks work that
# changed nothing.
#
# THIS NARROWS WHEN THE CHECK FIRES. IT DOES NOT LOOSEN WHAT IT CHECKS:
#   * a NEW ticket (absent from the base ref) is ALWAYS fully checked — no grandfathering;
#   * ANY change to work_class / repo / branch / difficulty / substrate / substrate-novel /
#     substrate-retest / parked, or to the SET of owns paths, is fully checked exactly as today;
#   * LOSING a D&S section is fully checked (a ratchet — gaining one can never make a verdict
#     worse, losing one always can);
#   * nothing is added to the "pass" side: a grandfathered ticket is SKIPPED, never asserted green.
#
# COMPARISON IS SEMANTIC, NOT BYTES. Values come from `_field` — the SAME line reader the checks
# themselves consume, so "the inputs did not change" is literally true of the checks that run.
# `owns:` compares as a SET of repo-relative paths, so a reorder, or rewriting an ABSOLUTE
# dev-box path to its repo-relative form, denotes the same owned files and stays grandfathered.
# Byte comparison was rejected: it is exactly the rule that already failed.
_SUBSTRATE_RELEVANT_KEYS="work_class repo branch difficulty substrate substrate-novel substrate-retest parked"

# _repo_rel <path> -> the repo-relative path this entry DENOTES.
# An ABSOLUTE owns entry is malformed by this gate's own owns-format rule, so rewriting one to the
# repo-relative path it denotes changes NO owned file — and must therefore not re-open the
# ticket's unrelated debt (that would be the same defect this scope fix exists to close, one level
# down). The leading components are dropped one at a time until the remainder EXISTS in the repo;
# an absolute path that resolves nowhere here is left ALONE, so it compares as different and the
# ticket is CHECKED. Fail-closed on ambiguity.
_repo_rel(){
  local p="${1#./}" rest
  case "$p" in
    /*) rest="${p#/}"
        while [ -n "$rest" ]; do
          [ -e "$ROOT/$rest" ] && { printf '%s' "$rest"; return 0; }
          case "$rest" in */*) rest="${rest#*/}";; *) break;; esac
        done
        printf '%s' "$p"; return 0 ;;
    *)  printf '%s' "$p" ;;
  esac
}

# _norm_owns <owns-value> -> the owned paths as a comparable, repo-relative, sorted SET.
_norm_owns(){
  local e out=""
  while IFS= read -r e; do
    e="$(printf '%s' "$e" | sed 's#^[[:space:]]*##; s#[[:space:]]*$##')"
    [ -n "$e" ] || continue
    out="$out$(_repo_rel "$e")"$'\n'
  done < <(printf '%s\n' "${1:-}" | tr ',' '\n')   # trailing \n: `read` drops an unterminated last field
  printf '%s' "$out" | grep -v '^[[:space:]]*$' | LC_ALL=C sort | paste -sd, - 2>/dev/null
}

_ds_present(){ grep -qiE '##[[:space:]]*dependencies[[:space:]]*&[[:space:]]*sequence|^ds:' "$1"; }

# _ticket_fingerprint <file> -> the verdict-relevant inputs, one key per line.
_ticket_fingerprint(){
  local f="$1" k
  for k in $_SUBSTRATE_RELEVANT_KEYS; do printf '%s=%s\n' "$k" "$(_field "$f" "$k")"; done
  printf 'owns=%s\n' "$(_norm_owns "$(_field "$f" owns)")"
}

# _ticket_grandfathered <repo-rel-path> <worktree-file> — 0 iff this PR changed nothing the
# per-ticket verdict depends on. FAIL CLOSED: any doubt (no base sha, unreadable base blob,
# mktemp failure) returns non-zero, i.e. CHECK IT.
_ticket_grandfathered(){
  local rel="$1" f="$2" tmp same=1
  [ -n "${_SCOPE_BASE:-}" ] || return 1
  git -C "$ROOT" cat-file -e "${_SCOPE_BASE}:${rel}" 2>/dev/null || return 1  # NEW ticket -> check
  tmp="$(mktemp 2>/dev/null)" || return 1
  if ! git -C "$ROOT" show "${_SCOPE_BASE}:${rel}" >"$tmp" 2>/dev/null; then rm -f "$tmp"; return 1; fi
  [ "$(_ticket_fingerprint "$tmp")" = "$(_ticket_fingerprint "$f")" ] || same=0
  if _ds_present "$tmp" && ! _ds_present "$f"; then same=0; fi   # ratchet: losing D&S always REDs
  rm -f "$tmp"
  [ "$same" -eq 1 ]
}

_check_ticket(){
  local f="$1" t="$2"
  if _is_parked "$f"; then info "skip $t (parked — staged, not live)"; return; fi

  local wc repo owns branch
  wc="$(_field "$f" work_class)"; repo="$(_field "$f" repo)"
  owns="$(_field "$f" owns)";     branch="$(_field "$f" branch)"

  [ -n "$branch" ] || red "$t: missing 'branch:' field"
  [ -n "$owns" ]   || red "$t: missing 'owns:' field"

  if [ -z "$wc" ]; then
    red "$t: missing 'work_class:' field (one of: $VALID_WORK_CLASSES)"
  elif ! grep -qw -- "$wc" <<<"$VALID_WORK_CLASSES"; then
    red "$t: work_class '$wc' is not one of: $VALID_WORK_CLASSES"
  fi

  if [ -n "$repo" ] && ! grep -qw -- "$(tr 'A-Z' 'a-z' <<<"$repo")" <<<"$VALID_REPOS"; then
    red "$t: repo '$repo' is not one of: $VALID_REPOS (see fleet/repo-registry.sh)"
  fi

  # owns-format: comma-separated RELATIVE paths; no absolutes, no whitespace inside a path.
  local IFS=,; local p
  for p in $owns; do
    p="$(printf '%s' "$p" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -n "$p" ] || continue
    case "$p" in
      /*) red "$t: owns entry '$p' is an ABSOLUTE path (must be repo-relative)" ;;
      *[[:space:]]*) red "$t: owns entry '$p' contains whitespace (comma-separate paths)" ;;
    esac
  done
  unset IFS

  # SUBSTRATE-FIRST [[adopt-substrate-build-only-novel-slice]] — a ticket whose work_class means
  # "write non-trivial new code" must answer the PRIOR question (what established EXTERNAL tool
  # covers this, and why not adopt it) before any build option is chosen. Marker-independent:
  # answerable from the ticket file + fleet/state/EVAL-REGISTRY.md alone, so it belongs in CI.
  # DELEGATED, not reimplemented — fleet/checks/substrate-first-gate.sh is the single rule module,
  # so the rule cannot drift between this scope check and any other caller. DIFF-SCOPED: this only
  # runs on tickets CHANGED in the PR (cmd_board loops over _scoped_board_files), so existing
  # tickets are grandfathered and never retroactively red.
  # Capture the output; do NOT pipe (pipefail would inherit the gate's own exit 1).
  local _sub_out
  _sub_out="$(bash "$HERE/substrate-first-gate.sh" check "$f" 2>&1)"
  if [ $? -ne 0 ]; then
    while IFS= read -r _l; do [ -n "$_l" ] && red "${_l#  RED  }"; done <<<"$_sub_out"
  fi

  # D&S standing rule — accept it inline in the ticket (`ds:` block) or in a `prompt:` file.
  if ! grep -qiE '##[[:space:]]*dependencies[[:space:]]*&[[:space:]]*sequence|^ds:' "$f"; then
    local pr; pr="$(_field "$f" prompt)"
    if [ -n "$pr" ] && [ -f "$ROOT/$pr" ] && grep -qiE '##[[:space:]]*dependencies[[:space:]]*&[[:space:]]*sequence' "$ROOT/$pr"; then
      : # satisfied by the prompt file
    else
      red "$t: no Dependencies & Sequence section (standing rule)"
    fi
  fi
}

cmd_suites(){ printf '%s\n' "${CI_SUITES[@]}"; }

cmd_tests(){
  local s rc
  # REENTRANCY GUARD (RIG-REDS 2026-07-24, [[fleet-selfcheck-forkbomb-class]]).
  # `cmd_tests` runs fleet/tests/rig-ci.test.sh, and rig-ci.test.sh runs
  # fleet/checks/rig-ci-scope.sh — a self-referential edge of exactly the class
  # that produced the ~18,900-proc handoff<->gate fork bomb. It was the LAST
  # unguarded cycle in the fleet: fleet/checks/selfcheck-cycle.sh reported
  # `rig-ci-scope -> rig-ci.test -> rig-ci-scope` as UNGUARDED, which is why
  # selfcheck-cycle.test.sh (1c/1d) was red. Today the inner call happens to use
  # `syntax`/`board` against a temp COPY, but `run_scope` honours $RIG_CI_SCRIPT,
  # so nothing structurally stops a future edit from re-entering `tests` here.
  # Same shape as gate.sh's CHARON_GATE_ACTIVE: the outer run exports the flag,
  # any nested run short-circuits. Exported so it survives the `bash` below.
  if [ -n "${RIG_CI_TESTS_ACTIVE:-}" ]; then
    echo "rig-ci-scope: already inside a suite run (RIG_CI_TESTS_ACTIVE) — skipping nested re-entry" >&2
    return 0
  fi
  export RIG_CI_TESTS_ACTIVE=1
  for s in "${CI_SUITES[@]}"; do
    if [ ! -f "$ROOT/fleet/tests/$s" ]; then
      red "allowlisted suite missing: fleet/tests/$s"
      continue
    fi
    echo "--- fleet/tests/$s"
    bash "$ROOT/fleet/tests/$s"; rc=$?
    [ $rc -eq 0 ] || red "suite FAILED (rc=$rc): fleet/tests/$s"
  done
  return $RED
}

case "${1:-}" in
  changed)    cmd_changed ;;
  syntax)     cmd_syntax ;;
  shellcheck) cmd_shellcheck ;;
  board)      cmd_board ;;
  suites)     cmd_suites ;;
  tests)      cmd_tests ;;
  *) echo "usage: rig-ci-scope.sh {changed|syntax|shellcheck|board|suites|tests}" >&2; exit 2 ;;
esac
exit $RED
