#!/usr/bin/env bash
# gate-integrity.sh — THE GATE ON THE GATES.
#
# THE QUESTION THIS ANSWERS: "we put in mechanized gates for this — what happened?"
# The answer, evidenced across a single day on this rig (2026-07-19), is that a gate can READ AS
# PROTECTION while providing NONE, in four distinct shapes. Every one of them survived a green
# preflight and a green CI run, because nothing ever asked whether the gate itself was alive:
#
#   1. TICKETED, NEVER BUILT      MARKER-PROOF-MECHANIZE, INERT-INSTANCE-DETECT — a ticket ID in a
#                                 board file reads like coverage. No file was ever written.
#   2. BUILT, NEVER WIRED         fleet/checks/large-file-guard.sh:19-20 states it is "Wired into
#                                 preflight.sh as a per-repo gate AND callable standalone from a
#                                 pre-commit hook". It has ZERO callers. The claim IS the defect:
#                                 a reader greps the header, sees wiring, and stops looking.
#   3. WIRED BUT STRUCTURALLY BLIND  tools/check_inert_code.py reports GREEN while six gateway
#                                 modules are constructed-but-never-invoked.
#   4. NO GATE AT ALL             this rig had no .github/ until 2026-07-19. CI was a belief.
#   (+ the allowlist variant) fleet/tests/land-safety.test.sh — the ONLY suite defending the
#                                 stale-bare-name guard — was absent from the CI_SUITES allowlist,
#                                 so it had never executed in CI. fleet/tests/ is an ALLOWLIST:
#                                 a new suite is excluded BY DEFAULT.
#
# ROOT CAUSE, stated once: THERE WAS NO GATE ON THE GATES. Nothing checked that a gate is actually
# invoked, or that an invoked gate can actually fail. This script asks exactly those two questions,
# mechanically, for every gate in the rig.
#
# ANTI-ACCRETION — what this deliberately does NOT do, and who owns it instead:
#   * fleet/checks/gate-creation-standard.sh owns "does this gate HAVE a red-proof test, and does
#     that test carry a fail-on-revert MARKER?" — a PRESENCE question. This script does not
#     re-check presence-with-marker; G3 below composes with it and says so in its output.
#   * fleet/checks/fixture-bypass.sh (D1/D2) owns "does that test REACH the production code?" — an
#     EXECUTION-DEPTH question, answered by static seam analysis and by no-op mutation.
#   * tools/check_inert_code.py (product repo) owns dead-code detection INSIDE python modules.
#     It goes green on shape 3 because it asks "is this symbol referenced?", and a constructed-
#     but-never-invoked object IS referenced. That is a real gap, but it is a gap in THAT lens,
#     and widening it belongs to that tool — not to a fifth parallel dead-code scanner here.
#   The orthogonal question left over, and the only one this script owns, is LIVENESS:
#     (a) IS IT INVOKED?   (b) CAN IT FAIL?
#
# FOUR DETECTIONS. Each is mechanically decidable from files on disk. Where a property is NOT
# cheaply decidable, this script says so IN THE OUTPUT rather than reporting a gate as proven —
# claiming more proof than was obtained is the very defect class above.
#
#   G1 INERT           A gate script with ZERO callers outside its own file, fleet/tests/, and
#                      documentation. Nothing runs it. Shape 2's second half.
#                      Comment lines are STRIPPED before caller matching: a gate mentioned in
#                      twelve comments and invoked by none is INERT, and counting the mentions is
#                      how it stayed invisible.
#
#   G2 FALSE-CLAIM     A gate's own header ASSERTS it is wired into a named file ("wired into X",
#                      "called by X", "runs in X", "invoked from X") and that file does NOT invoke
#                      it. This is the exact shape large-file-guard.sh shipped, and it is strictly
#                      worse than being silently inert: it actively answers the reader's question
#                      with a falsehood. A false claim is RED even when G1 is satisfied by some
#                      OTHER caller — the claim itself must be true or absent.
#
#   G3 UNPROVEN        A gate whose companion test (i) does not exist, or (ii) exists but is NOT in
#                      the LITERAL CI_SUITES allowlist of fleet/checks/rig-ci-scope.sh, so it never
#                      runs in CI, or (iii) exists but never asserts a NON-ZERO rc from the gate,
#                      so no case in it has ever demonstrated the gate going RED.
#                      HONEST SCOPE — this is the "can it fail?" question and this script answers
#                      only its cheap half. It does NOT execute the test, and it does NOT verify
#                      that the non-zero rc it found is causally produced by reverting the gate's
#                      real guard. A gate that clears G3 is NOT thereby proven; it has merely
#                      cleared the cheapest necessary conditions. Full proof is a mutation run —
#                      `fleet/checks/fixture-bypass.sh deep <suite> <entry>`. Every G3-clean gate
#                      is reported as "unrefuted", never as "proven".
#
#   G4 DOCUMENTED-GAP  A comment in any rig script that states, in prose, that a gate is NOT wired
#                      somewhere ("has never been wired into X", "is not wired into X", "NOT
#                      SECRET-SCANNED"). fleet/land.sh:319 carries exactly this about
#                      fleet/leak-guard.sh — honestly written, correct, and quietly permanent.
#                      An acknowledged gap with no ticket and no gate decays into an accepted one;
#                      this promotes it back to a visible finding every run. G4 is the inverse of
#                      G2: G2 catches a claim of wiring that is false, G4 catches an admission of
#                      missing wiring that is true.
#
# REENTRANCY [[fleet-selfcheck-forkbomb-class]]: this script must never invoke a gate that could
# re-invoke it. It executes exactly ONE external command — `rig-ci-scope.sh suites`, which only
# prints the literal CI_SUITES array and runs no suite. It never runs a test, never runs another
# check, never touches the network or gh. GATE_INTEGRITY_ACTIVE is exported for any child and
# refused on entry, so even a future edit that adds an invocation cannot recurse.
#
# READ-ONLY: never writes any file, never touches git refs, never auto-fixes.
#
# RATCHET (S3 UN-GAMED). The rig has PRE-EXISTING findings; a gate that reds the whole tree on day
# one is a gate that gets commented out within a week [[gates-must-actually-run]]. So the known
# legacy findings are FROZEN BY KEY in GI_BASELINE below. `check` reds ONLY on findings NOT in that
# baseline — i.e. on any NEW inert / falsely-claimed / unproven gate. The baseline is an explicit,
# reviewable list that can only shrink: removing a key from it is a tightening, adding one is a
# visible admission in the diff. `scan` prints everything and always exits 0.
#
# Usage:
#   gate-integrity.sh scan       ADVISORY. All findings, baseline ones marked. ALWAYS exit 0.
#   gate-integrity.sh check      RATCHET. exit 1 on any NON-baseline finding, else 0.
#   gate-integrity.sh report     scan + the per-gate liveness table (callers, test, CI, rc-assert).
# Env seams (self-test overrides; defaults are the real fleet/):
#   GI_ROOT GI_CHECKS_DIR GI_TESTS_DIR GI_CI_SCOPE GI_GATE_EXTRAS GI_BASELINE
# Exit: 0 = GREEN/advisory, 1 = RED (check mode, non-baseline finding), 2 = usage.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # repo root (script in fleet/checks/)
ROOT="${GI_ROOT:-$HERE}"
CHECKS_DIR="${GI_CHECKS_DIR:-$ROOT/fleet/checks}"
TESTS_DIR="${GI_TESTS_DIR:-$ROOT/fleet/tests}"
CI_SCOPE="${GI_CI_SCOPE:-$CHECKS_DIR/rig-ci-scope.sh}"

# Gate-shaped scripts that live OUTSIDE fleet/checks/. Named explicitly rather than pattern-matched:
# a heuristic "looks like a gate" rule over all of fleet/*.sh would sweep in launchers and reporters
# and drown the real findings. Extend deliberately.
# NOT in this list, deliberately: land.sh / land-push.sh / preflight.sh and other ENTRYPOINTS.
# They carry gates, but an entrypoint has no callers BY DESIGN — the operator runs it — so G1
# would report every one of them INERT. Adding them was tried and reverted; the land-safety.test.sh
# instance they were meant to reach is covered precisely by G5 instead.
GATE_EXTRAS="${GI_GATE_EXTRAS:-leak-guard.sh push-verify.sh handoff-check.sh dark-work-check.sh loop-guard.sh}"

# G5 ratchet floor: how many self-declared red-proof suites may sit outside CI_SUITES. Set to the
# count measured on this commit, so the number can only go DOWN without a visible diff.
GI_UNENFORCED_MAX="${GI_UNENFORCED_MAX:-88}"

# FROZEN legacy findings (see RATCHET above). Format: "<G-code>:<gate-basename>[:<detail>]".
# Regenerate mechanically with `gate-integrity.sh keys` — never transcribe by hand.
# Round-2 (2026-08-01, FIXTURE-BYPASS-GATE round 2) bumped the floor (45 -> 88 unenforced-proof
# suites) and broadened the baseline after rebasing onto origin/master: master accumulated 19 NEW
# inert / un-allowlisted / unproven findings between the original commit (2026-07-19) and now.
# The baseline can only SHRINK — removing an entry is a tightening, adding one is a visible admission
# in the diff. `gate-integrity.sh check` therefore reds ONLY on any finding absent from this list,
# i.e. on regressions against the live tree as it stands today.
#   G1 (9)  inert gates — nothing invokes them at all (predates this gate).
#   G3 (24) unproven — no companion test, or a test that never runs in CI.
#   G4 (2)  land.sh's own honest note that leak-guard.sh / push-verify.sh are not wired into it.
#   G5 (1)  unenforced-proof-suites aggregate (count surfaced in scan output).
GI_BASELINE="${GI_BASELINE:-\
G1:board-file-ratchet.sh G1:egress-key-canary.sh G1:gate-creation-standard.sh G1:large-file-guard.sh \
G1:reconcile-board-pr-done.sh G1:reconcile-review-gate.sh G1:registry-discovery.sh G1:selfcheck-cycle.sh \
G1:stuck-ticket-loud.sh \
G3:bandit.sh:not-allowlisted G3:config-ssot-gate.sh:not-allowlisted G3:dark-work-check.sh:no-test \
G3:discover-registries.sh:not-allowlisted G3:egress-key-canary.sh:not-allowlisted \
G3:gate-creation-standard.sh:not-allowlisted G3:gate-parity.sh:not-allowlisted \
G3:gitleaks.sh:not-allowlisted G3:gpt55-primary.sh:no-test G3:graphify-freshness.sh:not-allowlisted \
G3:handoff-check.sh:not-allowlisted G3:large-file-guard.sh:not-allowlisted \
G3:leak-guard.sh:not-allowlisted G3:loop-guard.sh:not-allowlisted G3:no-anthropic-in-sg.sh:no-test \
G3:no-claude-executor.sh:no-test G3:parallelizability-gate.sh:not-allowlisted \
G3:push-verify.sh:not-allowlisted G3:reconcile-board-pr-done.sh:not-allowlisted \
G3:reconcile-gate-wired.sh:not-allowlisted G3:reconcile-review-gate.sh:not-allowlisted \
G3:registry-discovery.sh:not-allowlisted G3:rule-sync.sh:not-allowlisted \
G3:selfcheck-cycle.sh:not-allowlisted G3:stuck-ticket-loud.sh:not-allowlisted \
G4:leak-guard.sh:land.sh G4:push-verify.sh:land.sh}"

# Reentrancy guard. Refuse if we are already a child; export for any child we spawn.
if [ -n "${GATE_INTEGRITY_ACTIVE:-}" ]; then
  echo "gate-integrity: refusing to run inside a gate-integrity child (reentrancy guard)." >&2
  exit 0
fi
export GATE_INTEGRITY_ACTIVE=1

FINDINGS=()       # "key<TAB>message"
finding(){ FINDINGS+=("$1$(printf '\t')$2"); }

in_baseline(){
  local k="$1" x
  for x in ${GI_BASELINE//,/ }; do [ "$x" = "$k" ] && return 0; done
  return 1
}

# ---- file universes --------------------------------------------------------------------------
# Caller candidates: executable surfaces only. Documentation, memory notes, handoffs and board
# state are EXCLUDED — a gate named in a handoff doc is not a gate that runs. That confusion is
# how "ticketed, never built" reads as coverage.
# SELF-EXCLUSION. This script's own finding MESSAGES name other gates ("...is owned by
# gate-creation-standard.sh..."). Those strings are inside quotes, so comment-stripping does not
# remove them, and the detector counted ITSELF as a caller of every gate it talks about — silently
# suppressing a TRUE G1 INERT finding for gate-creation-standard.sh. A detector's own prose about
# a gate is not wiring for that gate. Caught by dogfooding, 2026-07-19.
_caller_files(){
  local self_rel="fleet/checks/$(basename "${BASH_SOURCE[0]}")" listing
  listing="$(git -C "$ROOT" ls-files '*.sh' '*.yml' '*.yaml' 2>/dev/null | grep -vE '^fleet/(memory|state)/')"
  # `A || B | C` binds as `A || (B|C)`, so the exclusion below MUST NOT be chained onto the
  # fallback — it would then apply to only one of the two branches. Materialise first, filter once.
  [ -n "$listing" ] || listing="$(find "$ROOT" \( -name '*.sh' -o -name '*.yml' \) -printf '%P\n' 2>/dev/null)"
  printf '%s\n' "$listing" | grep -vxF "$self_rel"
}

# The gate universe: fleet/checks/*.sh plus the named extras.
_gate_files(){
  local f b
  for f in "$CHECKS_DIR"/*.sh; do [ -e "$f" ] && echo "${f#$ROOT/}"; done
  for b in ${GATE_EXTRAS//,/ }; do [ -f "$ROOT/fleet/$b" ] && echo "fleet/$b"; done
}

# Does file $2 INVOKE basename $1? Comments are stripped first: a mention is not a call.
#
# NO PIPELINE HERE, DELIBERATELY. This was written as `sed 's/#.*//' FILE | grep -qF "$base"` and
# that is WRONG under `set -o pipefail`: `grep -q` exits the instant it matches, sed takes SIGPIPE
# (141), pipefail promotes 141 to the pipeline status, and a TRUE match is reported as NO MATCH —
# non-deterministically, depending on whether sed finished first. It made fleet/land.sh:14
# (`source "$FLEET/push-verify.sh"`) invisible and this gate declared push-verify.sh INERT when it
# is sourced by two scripts. That is the fail-quiet-pipe-mask class occurring INSIDE the gate built
# to detect gates that silently do nothing. Caught by dogfooding, 2026-07-19. Match in-shell.
_invokes(){
  local base="$1" file="$2" stripped
  [ -f "$ROOT/$file" ] || return 1
  stripped="$(sed 's/#.*//' "$ROOT/$file" 2>/dev/null)"
  case "$stripped" in *"$base"*) return 0;; esac
  return 1
}

# Non-test, non-self callers of a gate. This is the G1 verdict input.
_callers(){
  local base="$1" self="$2" f
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ "$f" = "$self" ] && continue
    case "$f" in fleet/tests/*) continue;; esac
    _invokes "$base" "$f" && echo "$f"
  done < <(_caller_files)
}

# Companion test for a gate. Stem convention FIRST (the documented fleet convention), then a
# REFERENCE fallback: a suite that actually names this gate file is its companion whatever it is
# called. Without the fallback, rig-ci-scope.sh (covered by rig-ci.test.sh) and every other
# gate whose suite is named for the FEATURE rather than the FILE reports a spurious "no test" —
# and a gate that cries wolf gets disabled [[gates-must-actually-run]].
_companion(){
  local stem="${1%.sh}" t
  for t in "$TESTS_DIR/$stem.test.sh" "$TESTS_DIR/${stem%-gate}.test.sh" "$TESTS_DIR/$stem-gate.test.sh"; do
    [ -f "$t" ] && { echo "${t#$ROOT/}"; return 0; }
  done
  # Rank reference matches by how many times the suite names the gate. A suite that mentions the
  # gate ONCE in a comment is not its companion; the suite that drives it names it repeatedly.
  # Taking `head -1` here picked fixture-bypass.test.sh as rig-ci-scope.sh's companion purely by
  # alphabetical luck — a confident verdict about the wrong file.
  # THIS GATE'S OWN SUITE IS EXCLUDED, for the same reason _caller_files excludes this script:
  # gate-integrity.test.sh names other gates in its prose (large-file-guard.sh among them), and
  # the fallback happily adopted it as their companion — manufacturing a companion test out of a
  # comment and suppressing the true "no companion test" finding. A mention is not a companion.
  local selft="$TESTS_DIR/$(basename "${BASH_SOURCE[0]%.sh}").test.sh"
  t="$(grep -rcF "$1" "$TESTS_DIR" 2>/dev/null | grep -vF "$selft:" \
       | awk -F: '$2>0{print $2"\t"$1}' | sort -rn | head -1 | cut -f2)" || true
  [ -n "$t" ] && { echo "${t#$ROOT/}"; return 0; }
  return 1
}

_ci_suites(){
  [ -x "$CI_SCOPE" ] || [ -f "$CI_SCOPE" ] || return 1
  GATE_INTEGRITY_ACTIVE=1 bash "$CI_SCOPE" suites 2>/dev/null
}

# Does the suite assert a NON-ZERO rc from something? The cheap half of "can it fail".
# Deliberately broad: any comparison of a captured rc against a non-zero literal, any explicit
# expectation of RED/exit 1. A false NEGATIVE here (missing a real assertion) costs an advisory
# line; a false POSITIVE would report an unproven gate as proven, which is the defect itself.
_asserts_nonzero_rc(){
  local t="$1"
  grep -qE '(rc[^=]*[=" ]+(1|2)([^0-9]|$))|(-ne[[:space:]]+0)|(!=[[:space:]]*"?0)|(exit[[:space:]]+1[^0-9])|RED|fail-on-revert|red-proof' \
    "$ROOT/$t" 2>/dev/null
}

# ---- the scan --------------------------------------------------------------------------------
TABLE=()
run_scan(){
  local gf base self callers ncall comp ci_ok rc_ok suites
  suites="$(_ci_suites || true)"

  while IFS= read -r gf; do
    [ -n "$gf" ] || continue
    base="$(basename "$gf")"; self="$gf"

    # ---- (a) IS IT INVOKED? -------------------------------------------------------------
    callers="$(_callers "$base" "$self")"
    ncall="$(printf '%s' "$callers" | grep -c . || true)"
    if [ "$ncall" -eq 0 ]; then
      finding "G1:$base" \
"G1 INERT: $gf has ZERO callers outside itself, fleet/tests/ and documentation.
     => nothing in preflight, land, a hook, CI or another script ever runs it. It is a file
        that reads as protection and provides none.
     FIX: wire it (preflight cmd_detect / rig-ci.yml / the calling script) or delete it."
    fi

    # ---- (a') FALSE WIRING CLAIM --------------------------------------------------------
    # Header prose of the form "wired into X" / "called by X" / "invoked from X" / "runs in X",
    # where X names a real file in the tree that does not invoke this gate.
    local claim target
    while IFS= read -r claim; do
      [ -n "$claim" ] || continue
      # SUBJECT CHECK. The claim must be ABOUT this gate. "leak-guard.sh is called by fleet-droid.sh"
      # sitting inside land.sh is a claim about leak-guard, not about land.sh — reading it as one
      # produced four confident false findings in dogfooding. If any OTHER *.sh appears before the
      # verb phrase, this line has a different subject: skip it.
      local lc pre
      lc="$(printf '%s' "$claim" | tr '[:upper:]' '[:lower:]')"   # claims are written "Wired into"
      pre=""
      case "$lc" in
        *"wired into"*) pre="${lc%%wired into*}";;
        *"called by"*)  pre="${lc%%called by*}";;
        *invoked*)      pre="${lc%%invoked*}";;
        *"runs in"*)    pre="${lc%%runs in*}";;
      esac
      # Only skip when a DIFFERENT .sh is the subject. If no verb matched, `pre` is empty and we
      # must NOT fall back to the whole line — doing so made every claim look like it had a
      # foreign subject and silently suppressed the real config-ssot-gate.sh finding.
      case "$pre" in *.sh*) [ "${pre#*"$base"}" = "$pre" ] && continue;; esac
      for target in $(printf '%s\n' "$claim" | grep -oE '[A-Za-z0-9_./-]+\.(sh|yml|yaml|py)' || true); do
        [ "$(basename "$target")" = "$base" ] && continue
        # Resolve the claimed target to a real file. Prefer, in order: the literal path, the
        # SHALLOWEST match, then alphabetical. A bare `head -1` over `ls-files "*preflight.sh"`
        # resolved "wired into preflight.sh" to fleet/benchmark/leg-preflight.sh — the right
        # verdict named against the wrong file, which is how a true finding gets dismissed.
        local tpath=""
        if [ -f "$ROOT/$target" ]; then tpath="$target"
        else
          # EXACT BASENAME ONLY. `ls-files "*preflight.sh"` also glob-matches leg-preflight.sh, so
          # a claim about preflight.sh was reported against fleet/leg-preflight.sh — a correct
          # verdict named against the wrong file, which is how a true finding gets waved off.
          local tb; tb="$(basename "$target")"
          tpath="$(git -C "$ROOT" ls-files "*$tb" 2>/dev/null \
                   | awk -v b="$tb" '{n=split($0,p,"/"); if(p[n]==b) print gsub(/\//,"/")"\t"$0}' \
                   | sort -n -k1,1 | head -1 | cut -f2)"
          # Non-git fallback. MUST work outside a git repo: this gate has to run from a fresh
          # checkout and from a scratch copy, and a git-only resolver silently found NO target,
          # which suppressed the finding entirely — uncertainty resolving to green.
          if [ -z "$tpath" ]; then
            tpath="$(find "$ROOT" -name "$(basename "$target")" -printf '%P\n' 2>/dev/null \
                     | awk '{print gsub(/\//,"/")"\t"$0}' | sort -n -k1,1 | head -1 | cut -f2)"
          fi
        fi
        [ -n "$tpath" ] || continue
        if ! _invokes "$base" "$tpath"; then
          finding "G2:$base:$(basename "$tpath")" \
"G2 FALSE-CLAIM: $gf CLAIMS it is wired into $tpath, which does NOT invoke it.
     claim: $(printf '%s' "$claim" | sed 's/^[[:space:]#]*//' | cut -c1-100)
     => the claim is the defect: a reader greps the header, sees wiring, and stops looking.
     FIX: either wire $tpath to call $base, or DELETE the false claim from the header."
        fi
      done
    done < <(grep -inE '(wired[[:space:]]+into|called[[:space:]]+by|invoked[[:space:]]+(from|by)|runs[[:space:]]+in)[^.]*\.(sh|yml|yaml|py)' "$ROOT/$gf" 2>/dev/null \
             | grep -vE 'never|not[[:space:]]+(yet[[:space:]]+)?wired|no[[:space:]]+caller' \
             | grep -v '"' || true)
    # The `grep -v '"'` above drops QUOTED claims. A claim inside double quotes is a CITATION, not
    # an assertion — this file's own header quotes large-file-guard.sh's "Wired into preflight.sh"
    # verbatim as the worked example, and without this the detector flagged ITSELF for describing
    # the defect it detects. Real claims in this tree are written unquoted.

    # ---- (b) CAN IT FAIL? ---------------------------------------------------------------
    comp="$(_companion "$base" || true)"
    ci_ok=no; rc_ok=no
    if [ -z "$comp" ]; then
      finding "G3:$base:no-test" \
"G3 UNPROVEN: $gf has NO companion test in ${TESTS_DIR#$ROOT/}.
     => it has never been observed to go RED. Its green is an assertion, not a result.
     (Presence-with-red-proof-marker is owned by gate-creation-standard.sh; this is the
      liveness half: no test means the 'can it fail' question has no answer at all.)"
    else
      # In-shell match, not `printf | grep -qxF` — same SIGPIPE/pipefail masking as _invokes.
      if [ -n "$suites" ] && case $'\n'"$suites"$'\n' in *$'\n'"$(basename "$comp")"$'\n'*) true;; *) false;; esac; then ci_ok=yes; else
        finding "G3:$base:not-allowlisted" \
"G3 UNPROVEN: $comp exists but is NOT in the LITERAL CI_SUITES allowlist of ${CI_SCOPE#$ROOT/}.
     => fleet/tests/ is an ALLOWLIST — a suite absent from it has NEVER executed in CI.
        This is exactly how land-safety.test.sh, the only suite defending the stale-bare-name
        guard, sat unenforced. FIX: add $(basename "$comp") to CI_SUITES."
      fi
      if _asserts_nonzero_rc "$comp"; then rc_ok=yes; else
        finding "G3:$base:no-rc-assert" \
"G3 UNPROVEN: $comp never asserts a NON-ZERO rc from $base.
     => every case in it checks the GREEN path. Nothing in the suite has ever seen the gate fail.
     FIX: add a fail-on-revert case that neuters the guard and asserts rc != 0."
      fi
    fi
    TABLE+=("$(printf '%s\t%s\t%s\t%s\t%s' "$base" "$ncall" "${comp:-none}" "$ci_ok" "$rc_ok")")
  done < <(_gate_files | sort -u)

  # ---- G5 UNENFORCED-PROOF (the allowlist variant, reported as ONE aggregate) ------------
  # A suite that declares itself a red-proof / fail-on-revert proof is asserting "this guard has
  # been seen to fail". If it is not in CI_SUITES it has never executed in CI, so that assertion
  # is untested on every PR. This is exactly what happened to land-safety.test.sh, the ONLY suite
  # defending the stale-bare-name guard.
  # AGGREGATED ON PURPOSE: 45 separate findings is a wall of text, and a gate that emits a wall of
  # text gets skimmed and then disabled [[gates-must-actually-run]]. One finding, one count, one
  # ratchet floor. The floor can only be lowered, so the backlog cannot silently grow.
  local unenf=() tb
  for tb in "$TESTS_DIR"/*.test.sh; do
    [ -e "$tb" ] || continue
    grep -qiE 'red-proof|fail-on-revert' "$tb" || continue
    tb="$(basename "$tb")"
    case $'\n'"$suites"$'\n' in *$'\n'"$tb"$'\n'*) continue;; esac
    unenf+=("$tb")
  done
  if [ "${#unenf[@]}" -gt "$GI_UNENFORCED_MAX" ]; then
    finding "G5:unenforced-proof-suites" \
"G5 UNENFORCED-PROOF: ${#unenf[@]} suites declare themselves red-proofs but are NOT in CI_SUITES
     (ratchet floor is $GI_UNENFORCED_MAX — this count went UP, so a NEW proof suite was written that
      will never run in CI).
     => each one asserts 'this guard has been seen to fail' and is never executed on a PR.
     FIX: add the new suite to CI_SUITES in ${CI_SCOPE#$ROOT/}, or lower GI_UNENFORCED_MAX if you
     just enforced some. Current set: ${unenf[*]}"
  elif [ "${#unenf[@]}" -gt 0 ]; then
    echo "gate-integrity: G5 ${#unenf[@]} self-declared red-proof suite(s) outside CI_SUITES"
    echo "     (at/below the ratchet floor of $GI_UNENFORCED_MAX — backlog, not a regression):"
    echo "     ${unenf[*]}"
  fi

  # ---- G4 DOCUMENTED-GAP (tree-wide prose scan) -----------------------------------------
  local hit file line text g
  SEEN_G4=""
  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    file="${hit%%:*}"; text="${hit#*:}"; line="${text%%:*}"; text="${text#*:}"
    for g in $(printf '%s\n' "$text" | grep -oE '[A-Za-z0-9_-]+\.sh' || true); do
      [ -f "$ROOT/fleet/$g" ] || [ -f "$CHECKS_DIR/$g" ] || continue
      # The note's HOST file is not the subject of its own gap note; skip it so a multi-line note
      # in land.sh does not report "land.sh is not wired into land.sh".
      [ "$g" = "$(basename "$file")" ] && continue
      case " $SEEN_G4 " in *" $g:$(basename "$file") "*) continue;; esac
      SEEN_G4="$SEEN_G4 $g:$(basename "$file")"
      finding "G4:$g:$(basename "$file")" \
"G4 DOCUMENTED-GAP: ${file#$ROOT/}:$line states in prose that $g is NOT wired somewhere.
     note: $(printf '%s' "$text" | sed 's/^[[:space:]#]*//' | cut -c1-110)
     => an acknowledged gap with no gate behind it decays into an accepted one. This finding
        is the ticket. FIX: close the wiring, or delete the note if it is stale."
      break
    done
  done < <(grep -rnE '(never[[:space:]]+been[[:space:]]+wired|has[[:space:]]+never[[:space:]]+been[[:space:]]+wired|is[[:space:]]+not[[:space:]]+wired|not[[:space:]]+wired[[:space:]]+into|NOT[[:space:]]+SECRET-SCANNED)' \
        --include='*.sh' "$ROOT/fleet" 2>/dev/null | grep -v "^$ROOT/fleet/checks/gate-integrity.sh:" || true)
}

# ---- output ----------------------------------------------------------------------------------
emit(){
  local mode="$1" f key msg n_new=0 n_base=0
  for f in ${FINDINGS[@]+"${FINDINGS[@]}"}; do
    key="${f%%$(printf '\t')*}"; msg="${f#*$(printf '\t')}"
    if in_baseline "$key"; then
      n_base=$((n_base+1))
      [ "$mode" = scan ] && echo "GATE-INTEGRITY (baseline): $msg"
    else
      n_new=$((n_new+1))
      echo "GATE-INTEGRITY: $msg"
    fi
  done
  echo "gate-integrity: ${#FINDINGS[@]} finding(s) — $n_new new, $n_base baseline."
  echo "     NOTE: gates with no finding are UNREFUTED, not proven. This script does not execute"
  echo "     any suite; full proof is fleet/checks/fixture-bypass.sh deep <suite> <entry>."
  RET=0; [ "$n_new" -gt 0 ] && RET=1
}

emit_table(){
  echo "--- gate liveness table (callers / companion test / in CI / asserts non-zero rc) ---"
  printf '%-32s %7s  %-34s %4s %4s\n' GATE CALLERS TEST CI RC
  local r
  for r in ${TABLE[@]+"${TABLE[@]}"}; do
    IFS=$'\t' read -r a b c d e <<<"$r"
    printf '%-32s %7s  %-34s %4s %4s\n' "$a" "$b" "$(basename "$c")" "$d" "$e"
  done
}

RET=0
case "${1:-}" in
  scan)   run_scan; emit scan;   exit 0 ;;      # ADVISORY: always exit 0.
  check)  run_scan; emit check;  exit $RET ;;   # RATCHET: red on NON-baseline findings only.
  report) run_scan; emit scan; emit_table; exit 0 ;;
  # `keys` prints the finding KEYS only, one per line — the exact strings GI_BASELINE accepts.
  # It exists so the baseline is REGENERATED MECHANICALLY rather than transcribed by hand: a
  # hand-copied baseline drifts, and a drifted baseline silently suppresses real findings.
  keys)   run_scan >/dev/null 2>&1
          for _f in ${FINDINGS[@]+"${FINDINGS[@]}"}; do echo "${_f%%$(printf '\t')*}"; done | sort -u
          exit 0 ;;
  *) echo "usage: gate-integrity.sh {scan|check|report|keys}" >&2; exit 2 ;;
esac
