#!/usr/bin/env bash
# substrate-first-gate.test.sh — RED-PROOF / fail-on-revert suite for
# fleet/checks/substrate-first-gate.sh.
#
# red-proof: neuter the substrate requirement in substrate-first-gate.sh (make the missing
# `substrate:` field a pass) and cases R1-R8 below go GREEN -> this suite FAILS. That is the
# S1 evidence: the gate has been seen RED on the real failure shape, not on a tautology.
#
# HERMETIC: builds a throwaway board fixture + a throwaway EVAL-REGISTRY under mktemp -d.
# It never reads the live board, never touches fleet/state/, never hits the network.
#
# REENTRANCY [[fleet-selfcheck-forkbomb-class]]: this suite invokes ONLY the gate script
# directly. It must NEVER call rig-ci-scope.sh, validate_board.sh, preflight.sh or land*.sh
# — those invoke the gate, and a test that invokes its own caller is the fork bomb. The
# guard is also asserted positively by case G5.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$HERE/../checks/substrate-first-gate.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
BOARD="$TMP/board"; mkdir -p "$BOARD"
export SUBSTRATE_REGISTRY="$TMP/EVAL-REGISTRY.md"

PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "  ok   $1"; }
bad(){  FAIL=$((FAIL+1)); echo "  FAIL $1"; }

# --- fixture registry: one row per alignment class the gate must distinguish -------------
# NB: every fixture row is WELL-FORMED — 8 cells, a recognised alignment class, a resolvable
# evidence-link and a substantive reason. The MALFORMED rows the S1/S2/S3 cases need are added
# to a SEPARATE fixture below, so the well-formed path cannot be contaminated by them.
EV='fleet/checks/substrate_first_gate.py'
cat >"$SUBSTRATE_REGISTRY" <<REG
# EVAL-REGISTRY (fixture)
| tool | scope | date | verdict | alignment | reason | evidence-link | supersedes |
|---|---|---|---|---|---|---|---|
| Semgrep | AST linting of an HTTP choke point | 2026-07-20 | ADOPT | aligned | tested the real plugin-wrap framing against the taint mode rather than a full-embed strawman, and the ruleset covers the bare-name case | $EV | — |
| pre-commit | hook orchestration framework for repository-local checks | 2026-07-20 | ADOPT | aligned | hyphenated name pins the separator-splitting regression; the eval compared hook orchestration against the existing launcher rather than a rewrite | $EV | — |
| LiteLLM | Router cooldown as an optional plugin behind the stdlib core | 2026-07-13 | UNRESOLVED | drifted (prior evals never tested this framing) | prior rejections argued full-embed stack weight and never checked whether the Router is separable, which is a strawman dependency-weight objection rather than a tested one | $EV | — |
| tenacity | retry and backoff around provider calls | 2026-07-20 | candidate | mixed | genuinely embeddable and small, but the eval never settled whether the existing circuit breaker already covers the same ground on the hot path | $EV | — |
| Presidio | mentioned in passing while scoping a scrubber | 2026-07-20 | — | n-a | a tangential mention inside another document, carrying no verdict of its own on whether to adopt it for this or any scope | $EV | — |
REG

# --- MALFORMED-ROW fixture: every registry shape v1's awk mis-read as "aligned" ------------
BADREG="$TMP/EVAL-REGISTRY-malformed.md"
cat >"$BADREG" <<REG
# EVAL-REGISTRY (malformed fixture)
| tool | scope | date | verdict | alignment | reason | evidence-link | supersedes |
|---|---|---|---|---|---|---|---|
| UnknownAlign | some scope | 2026-07-20 | REJECTED | UNRESOLVED-TODO | the alignment cell is not one of the four classes the schema defines, so this row cannot be classified | $EV | — |
| ShortRow | s |
| Vendored\\|Copy | scope with an escaped pipe in the tool cell | 2026-07-20 | REJECTED | drifted | the markdown-escaped pipe used to shift every column by one so this drifted row read as aligned | $EV | — |
| NoReceipt | scope | 2026-07-20 | REJECTED | aligned | a fabricated row appended by the author of the ticket that cites it, carrying no evidence whatsoever | none | — |
| Featherless | chunked economy units | 2026-07-20 | REJECTED | aligned | real per-unit token totals show the smallest observed unit already exceeds the cap several times over | $EV | — |
\`\`\`
| FencedTool | inside a fenced code block | 2026-07-20 | ADOPT | aligned | this row is an EXAMPLE inside a code fence and must never be matched as a real registry row | $EV | — |
\`\`\`
REG

mk(){ # mk <name> <body...>
  local n="$1"; shift; printf '%s\n' "$@" >"$BOARD/$n.md"
}
# expect <RED|GREEN> <ticket> <label>
expect(){
  local want="$1" t="$2" label="$3" out rc
  out="$(bash "$GATE" check "$BOARD/$t.md" 2>&1)"; rc=$?
  local got=GREEN; [ "$rc" -ne 0 ] && got=RED
  if [ "$got" = "$want" ]; then ok "$label [$got]"
  else bad "$label — expected $want, got $got"; printf '%s\n' "$out" | sed 's/^/        /'; fi
}

echo "== substrate-first-gate: RED cases (the gate must refuse these) =="

# R1 — THE ORIGINAL FAILURE: a code-writing ticket with no substrate field at all.
mk NO-FIELD 'repo: charon-private' 'work_class: ci-infra' 'difficulty: 4' \
  'owns: src/charon/http_chokepoint.py' 'note: harden the HTTP choke point'
expect RED NO-FIELD "R1 code-writing ticket carries NO substrate: field"

# R2 — the field exists but is empty (the question skipped while looking answered).
mk EMPTY 'work_class: greenfield-feature' 'difficulty: 3' 'substrate:' 'owns: src/a.py'
expect RED EMPTY "R2 substrate: field present but EMPTY"

# R3 — THE REFRAME: names an in-tree module as if it were substrate. This is the exact
# 2026-07-19 shape (two BUILD options, neither external) and must not satisfy the gate.
mk REFRAME 'work_class: ci-infra' 'difficulty: 4' 'owns: fleet/checks/ast-linter.sh' \
  'substrate: fleet/checks/ast-linter.sh — reject — Option A patches it, Option B redesigns it wholesale'
expect RED REFRAME "R3 names an IN-TREE module as substrate (reframe defeated)"

# R3b — red-proofs the anti-reframe clause by its DIAGNOSTIC, not its exit code.
# Measured, not assumed: neutering the path clause left the whole suite green, because an
# in-tree name is ALSO caught by the owns-self-cite check (R3) and, failing that, by the
# no-registry-row check (an in-tree module never has a row). The clause's exit code is
# therefore redundant by construction. Its real contract is the MESSAGE: without it a
# reframed ticket is told "add an EVAL-REGISTRY row for src/charon/existing_helper.py",
# which is actively wrong advice that launders a build option into the registry. With it,
# the author is told the truth — this is a build option, not substrate. Assert the wording.
mk REFRAME2 'work_class: ci-infra' 'difficulty: 4' 'owns: src/charon/proxy.py' \
  'substrate: src/charon/existing_helper.py — adopt — we already have an internal helper module that does most of this so we will extend it'
# NB: capture to a variable, never `gate | grep -q`. Under `set -o pipefail` the pipeline
# inherits the gate's own exit 1, so a matching grep still reports failure — the fail-quiet
# pipe-mask class in fleet/state/GATE-GAP-LEDGER.tsv, met while writing this very test.
r3b_out="$(bash "$GATE" check "$BOARD/REFRAME2.md" 2>&1)"
case "$r3b_out" in
  *"IN-TREE module/path, not external substrate"*)
    ok "R3b in-tree path is diagnosed as a BUILD option, not sent to the registry" ;;
  *) bad "R3b wrong diagnostic — a reframed ticket would be told to register its own module" ;;
esac

# R4 — cites the very file it is about to write.
mk SELFCITE 'work_class: refactor' 'difficulty: 3' 'owns: src/charon/limiter.py' \
  'substrate: limiter.py — adopt — we already have a limiter module that covers all of this cleanly'
expect RED SELFCITE "R4 substrate names a path in the ticket's own owns:"

# R5 — external, plausible, but has NO row in the registry: the consult never happened.
mk NOROW 'work_class: money-path' 'difficulty: 4' 'owns: src/charon/ledger.py' \
  'substrate: Stripe — reject — their billing model does not fit a local-first per-token meter at all'
expect RED NOROW "R5 named tool has NO EVAL-REGISTRY row (consult not done)"

# R6 — cites a DRIFTED row as settled. The registry schema forbids exactly this.
mk DRIFTED 'work_class: routing' 'difficulty: 4' 'owns: src/charon/failover.py' \
  'substrate: LiteLLM — reject — already evaluated and rejected previously, so we hand-roll the cooldown'
expect RED DRIFTED "R6 cites a DRIFTED row as settled (must re-test)"

# R7 — cites an n-a row (a tangential mention) as if it were a verdict.
mk NAROW 'work_class: ci-infra' 'difficulty: 3' 'owns: src/charon/scrub.py' \
  'substrate: Presidio — reject — it was looked at before and did not seem like a fit for our needs'
expect RED NAROW "R7 cites an 'n-a' row as a verdict"

# R8 — N/A with no novel-slice justification: the cheapest possible escape hatch, closed.
mk NA-BARE 'work_class: greenfield-feature' 'difficulty: 4' 'owns: src/charon/novel.py' \
  'substrate: N/A'
expect RED NA-BARE "R8 'substrate: N/A' with no substrate-novel: reason"

# R9 — a one-word reason is a label, not an answer.
mk THIN 'work_class: refactor' 'difficulty: 3' 'owns: src/charon/x.py' \
  'substrate: Semgrep — reject — too slow'
expect RED THIN "R9 substrate reason too thin to be a reason"

# R10 — FAIL CLOSED: registry unreachable must RED, never silently pass (S2 non-vacuous).
mk CLOSED 'work_class: ci-infra' 'difficulty: 4' 'owns: src/a.py' \
  'substrate: Semgrep — adopt — covers the AST rules we would otherwise hand-roll, MIT, already packaged'
( export SUBSTRATE_REGISTRY="$TMP/does-not-exist.md"
  bash "$GATE" check "$BOARD/CLOSED.md" >/dev/null 2>&1 ) && \
  bad "R10 unreachable registry passed (fail-OPEN!)" || ok "R10 unreachable registry fails CLOSED [RED]"

echo "== substrate-first-gate: GREEN cases (the gate must not false-alarm) =="

# G1 — the compliant shape: external tool, ALIGNED row, real reason.
mk GOOD 'work_class: ci-infra' 'difficulty: 4' 'owns: src/charon/chokepoint.py' \
  'substrate: Semgrep — adopt — covers the AST rules we would otherwise hand-roll, has a maintained ruleset, and its taint mode already catches the bare-name urlopen case our own linter missed'
expect GREEN GOOD "G1 external tool + ALIGNED row + real reason"

# G2 — a drifted row IS citable once the ticket states how it re-tests the skipped framing.
mk RETEST 'work_class: routing' 'difficulty: 4' 'owns: src/charon/failover.py' \
  'substrate: LiteLLM — wrap-as-plugin — the prior rejection argued full-embed stack weight, never the plugin framing' \
  'substrate-retest: this ticket imports litellm.Router in isolation behind the stdlib core and measures import cost, which is the framing the drifted row says was skipped'
expect GREEN RETEST "G2 DRIFTED row + substrate-retest: accepted"

# G3 — N/A is legitimate for a genuinely novel slice, with a stated reason.
mk NOVEL 'work_class: greenfield-feature' 'difficulty: 4' 'owns: src/charon/novel.py' \
  'substrate: N/A' \
  'substrate-novel: outcome-graded routing across per-provider funding classes is the differentiating slice; no gateway ships grade-fed provider substitution, checked against the registry rows'
expect GREEN NOVEL "G3 N/A + substrate-novel: reason accepted"

# G4 — classes that dispatch no implementation are exempt (no false alarms on docs).
mk DOCSONLY 'work_class: docs' 'difficulty: 2' 'owns: docs/x.md'
expect GREEN DOCSONLY "G4 docs work_class exempt"
mk SMALLFIX 'work_class: bugfix' 'difficulty: 1' 'owns: src/charon/y.py'
expect GREEN SMALLFIX "G4b low-difficulty bugfix exempt"
mk PARKED 'work_class: ci-infra' 'difficulty: 4' 'parked: true' 'owns: src/a.py'
expect GREEN PARKED "G4c parked ticket exempt (staged, not live)"

# G4d — but a bugfix that is NOT small is gated: the 2026-07-19 failure was a "fix" that
# grew into ~900 LOC of bespoke machinery. Difficulty is what separates the two.
mk BIGFIX 'work_class: bugfix' 'difficulty: 4' 'owns: src/charon/big.py'
expect RED BIGFIX "G4d high-difficulty bugfix IS gated"

# G5 — reentrancy guard: a REAL nested invocation refuses instead of recursing, and refuses
# with a NON-ZERO rc. The marker must name a LIVE process that is itself running this gate,
# so stand one up rather than exporting a bare 1 (which is the S4 kill-switch shape, not
# nesting, and is asserted separately below).
cat >"$TMP/substrate-sleeper.sh" <<'SLEEP'
sleep 20
SLEEP
bash "$TMP/substrate-sleeper.sh" & g5_pid=$!
g5_out="$(SUBSTRATE_GATE_ACTIVE=$g5_pid bash "$GATE" check "$BOARD/NO-FIELD.md" 2>&1)"; g5_rc=$?
kill "$g5_pid" 2>/dev/null; wait "$g5_pid" 2>/dev/null
case "$g5_out" in
  *"reentrancy guard"*)
    [ "$g5_rc" -ne 0 ] \
      && ok "G5 nested invocation refused by reentrancy guard, NON-ZERO [rc=$g5_rc]" \
      || bad "G5 guard fired but exited 0 — a refusal that exits 0 IS a kill switch (S4)" ;;
  *) bad "G5 reentrancy guard did not fire on a live nested invocation" ;;
esac

# G8 — a HYPHENATED tool name must survive name extraction. Regression pin: the separator split
# used to accept a bare hyphen, turning "pre-commit" into "pre", which matched no registry row and
# produced a bogus "no row, evaluate it" RED for an ALIGNED, already-registered tool. Found in the
# end-to-end demo through the real CI path — the unit suite had no hyphenated name to catch it.
mk HYPHEN 'work_class: ci-infra' 'difficulty: 4' 'owns: src/charon/hooks.py' \
  'substrate: pre-commit — adopt — it already runs the hook orchestration we would otherwise hand-roll and is aligned in the registry'
expect GREEN HYPHEN "G8 hyphenated tool name resolves to its registry row"

# G6 — scan mode is ADVISORY: it must never exit non-zero, even over a board full of REDs.
if bash "$GATE" scan "$BOARD" >/dev/null 2>&1; then ok "G6 scan mode is advisory (rc 0 over a red board)"
else bad "G6 scan mode exited non-zero — it would false-block preflight"; fi

# =========================================================================================
# S1-S8 — RED-PROOF cases for the nine evasions found by adversarial review of v1 @ 981c287.
# Each one was REPRODUCED against v1 before the fix, and each fails if its fix is reverted.
# =========================================================================================
echo "== substrate-first-gate: adversarial-evasion RED-PROOFS (S1-S8) =="

expect_bad(){ # expect_bad <RED|GREEN> <ticket> <label>   — same as expect, malformed registry
  local want="$1" t="$2" label="$3" out rc
  out="$(SUBSTRATE_REGISTRY="$BADREG" bash "$GATE" check "$BOARD/$t.md" 2>&1)"; rc=$?
  local got=GREEN; [ "$rc" -ne 0 ] && got=RED
  if [ "$got" = "$want" ]; then ok "$label [$got]"
  else bad "$label — expected $want, got $got"; printf '%s\n' "$out" | sed 's/^/        /'; fi
}

# S1a — THE TABLE HEADER ROW. v1's awk set `worst` only for the four literal classes and
# END printed "aligned" whenever it was still empty, so the header row's alignment cell
# (the literal word "alignment") resolved to ALIGNED and `substrate: tool` went GREEN.
mk S1-HEADER 'work_class: money-path' 'difficulty: 5' 'owns: src/charon/t.py' \
  'substrate: tool — reject — the literal word tool is the header row of the markdown table itself and must never resolve to a citable row'
expect_bad RED S1-HEADER "S1a table HEADER row is not a citable ALIGNED row"

# S1b — an unrecognised alignment class must FAIL CLOSED, never default to the permissive value.
mk S1-UNKNOWN 'work_class: money-path' 'difficulty: 5' 'owns: src/charon/t.py' \
  'substrate: UnknownAlign — reject — its registry row carries an alignment class the schema does not define, which must be a hard red rather than a default'
expect_bad RED S1-UNKNOWN "S1b UNRECOGNISED alignment fails closed (never defaults to aligned)"

# S1c — a truncated row (fewer than 8 cells) must be MALFORMED, not short-read as aligned.
mk S1-SHORT 'work_class: money-path' 'difficulty: 5' 'owns: src/charon/t.py' \
  'substrate: ShortRow — reject — a truncated registry row has no alignment column at all so it cannot possibly be read as a settled aligned verdict'
expect_bad RED S1-SHORT "S1c truncated registry row is MALFORMED, not aligned"

# S1d — the escaped-pipe field shift. `Vendored\|Copy` moved every column right by one under
# awk -F'|', so a genuinely DRIFTED row read as aligned. Splitting on UNESCAPED pipes only
# keeps the columns aligned, so the row resolves to what it actually says: drifted.
mk S1-PIPE 'work_class: money-path' 'difficulty: 5' 'owns: src/charon/t.py' \
  'substrate: Vendored|Copy — reject — a markdown-escaped pipe in the tool cell must not shift the alignment column and launder this genuinely drifted row'
expect_bad RED S1-PIPE "S1d escaped pipe no longer shifts columns (drifted row stays drifted)"

# S2 — prefix matching. v1 accepted index(cell, want)==1, so `Feath` matched Featherless's
# ALIGNED row and `check` matched check-jsonschema's. Any short made-up token was substrate.
mk S2-PREFIX 'work_class: money-path' 'difficulty: 5' 'owns: src/charon/t.py' \
  'substrate: Feath — reject — this is merely a prefix of a registered tool name and names no tool that actually exists anywhere at all'
expect_bad RED S2-PREFIX "S2 prefix of a registered tool does NOT resolve (exact match only)"

# S3a — a fabricated row with no receipt. The review appended one line to the real registry
# and went green; the gate's own RED message told the author to do exactly that.
mk S3-NORECEIPT 'work_class: money-path' 'difficulty: 5' 'owns: src/charon/t.py' \
  'substrate: NoReceipt — reject — its registry row was appended by the ticket author and carries a placeholder evidence link rather than any citation'
expect_bad RED S3-NORECEIPT "S3a registry row with placeholder evidence-link is not citable"

# S3b — a row inside a ``` fence is documentation, not a registry row. v1's /^\|/ had no
# fence awareness, so an EXAMPLE row in the schema section was citable.
mk S3-FENCED 'work_class: money-path' 'difficulty: 5' 'owns: src/charon/t.py' \
  'substrate: FencedTool — reject — its only registry row sits inside a fenced code block as an illustration and is not a real row at all'
expect_bad RED S3-FENCED "S3b row inside a \`\`\` fence is NOT a registry row"

# S4 — the kill switch. v1 exited 0 when SUBSTRATE_GATE_ACTIVE was set in the environment,
# so exporting one variable greened every ticket, and rig-ci-scope.sh inherits the step env.
s4_out="$(SUBSTRATE_GATE_ACTIVE=1 bash "$GATE" check "$BOARD/NO-FIELD.md" 2>&1)"; s4_rc=$?
[ "$s4_rc" -ne 0 ] \
  && ok "S4 inherited SUBSTRATE_GATE_ACTIVE cannot green a RED ticket [rc=$s4_rc]" \
  || bad "S4 KILL SWITCH — an inherited env var made a known-RED ticket exit 0"
case "$s4_out" in
  *"ignoring inherited"*) ok "S4b the guard re-arms and says so instead of silently passing" ;;
  *) bad "S4b guard did not announce that it ignored the inherited marker" ;;
esac

# S5 — a CRLF ticket. v1's `case " $ALWAYS " in *" $wc "*` never matched `money-path\r`, so the
# ticket skipped the gate entirely while still passing rig-ci-scope.sh's enum check.
printf 'work_class: money-path\r\ndifficulty: 5\r\nowns: src/charon/t.py\r\n' >"$BOARD/S5-CRLF.md"
expect RED S5-CRLF "S5 CRLF line endings no longer make the gate skip"
printf 'work_class: money-path \ndifficulty: 5\nowns: src/charon/t.py\n' >"$BOARD/S5-WS.md"
expect RED S5-WS "S5b trailing whitespace on work_class no longer makes the gate skip"
# S5c — a ticket that cannot be parsed at all must RED, never skip (fail-closed).
printf 'work_class: money-path\nnote: unquoted: prose: with: colons\n  and a continuation\n' >"$BOARD/S5-UNPARSEABLE.md"
expect RED S5-UNPARSEABLE "S5c unparseable frontmatter REDs (never a silent skip)"

# S6 — filler. v1's only reason test was `>= 40 chars`, which 48 `x` and 50 `a` both pass.
pad_a="$(printf 'a%.0s' $(seq 1 120))"
mk S6-FILLER 'work_class: money-path' 'difficulty: 5' 'owns: src/charon/t.py' \
  "substrate: Semgrep — reject — $pad_a"
expect RED S6-FILLER "S6 a long run of one character is not a reason"
pad_x="$(printf 'x%.0s' $(seq 1 120))"
mk S6-RETEST-FILLER 'work_class: routing' 'difficulty: 5' 'owns: src/charon/f.py' \
  'substrate: LiteLLM — reject — the registry row for this tool is drifted and this ticket is going to hand roll the behaviour anyway' \
  "substrate-retest: $pad_x"
expect RED S6-RETEST-FILLER "S6b filler in substrate-retest: does not launder a DRIFTED row"

# S7 — self-declared class/difficulty. The 2026-07-19 incident was a security FIX that grew;
# `bugfix` + `difficulty: 2` reproduces it, and omitting difficulty was even cheaper.
mk S7-NODIFF 'work_class: tests' 'owns: src/charon/proxy.py'
expect RED S7-NODIFF "S7 a MISSING difficulty is not 'low' — it REDs"
mk S7-BADDIFF 'work_class: bugfix' 'difficulty: soon' 'owns: src/charon/proxy.py'
expect RED S7-BADDIFF "S7b a non-numeric difficulty REDs"
mk S7-DOCSCODE 'work_class: docs' 'difficulty: 2' 'owns: src/charon/whole_new_subsystem.py'
expect RED S7-DOCSCODE "S7c work_class 'docs' may not own a .py file"
mk S7-DOCSOK 'work_class: docs' 'difficulty: 2' 'owns: docs/adr/0017-x.md'
expect GREEN S7-DOCSOK "S7d work_class 'docs' owning only docs is still exempt"

# S8 — PARKED as a substring. v1 skipped any ticket with a `note:` field and the word PARKED
# anywhere in the file, so a live ticket mentioning a parked sibling skipped the gate.
mk S8-SUBSTRING 'work_class: money-path' 'difficulty: 5' 'owns: src/charon/t.py' \
  'note: active work, do not park' \
  'ds: unlike the PARKED sibling ticket, this one is live and must be gated'
expect RED S8-SUBSTRING "S8 the word PARKED in prose does not park a live ticket"
mk S8-REAL 'work_class: money-path' 'difficulty: 5' 'parked: true' 'owns: src/charon/t.py'
expect GREEN S8-REAL "S8b an explicit parked-true field still parks"

# S9 — the anti-reframe had the shape backwards: it rejected every scoped npm package and
# org/repo reference on `*/*` while a dotted in-tree module sailed through.
mk S9-SCOPED 'work_class: greenfield-feature' 'difficulty: 4' 'owns: src/charon/t.py' \
  'substrate: "@sinclair/typebox" — adopt — a real scoped npm package is external substrate and must be judged on its registry row, not rejected for containing a slash'
s9_out="$(bash "$GATE" check "$BOARD/S9-SCOPED.md" 2>&1)"
case "$s9_out" in
  *"IN-TREE module/path"*) bad "S9 a scoped npm package was still misread as an in-tree path" ;;
  *) ok "S9 a scoped npm package is not misread as an in-tree path" ;;
esac
mk S9-DOTTED 'work_class: greenfield-feature' 'difficulty: 4' 'owns: src/charon/t.py' \
  'substrate: charon.context_shaper — adopt — a dotted in-tree module is a build option wearing the substrate field name and must be caught'
s9b_out="$(bash "$GATE" check "$BOARD/S9-DOTTED.md" 2>&1)"
case "$s9b_out" in
  *"IN-TREE module/path"*) ok "S9b a dotted in-tree module IS caught by the anti-reframe filter" ;;
  *) bad "S9b dotted in-tree module escaped the anti-reframe filter" ;;
esac

# S3c — SAME-CHANGE PROVENANCE. The review's cheapest CRITICAL: append one row to the registry
# in the SAME PR and cite it. The gate's own RED message told the author to do exactly that.
# A row and the ticket that relies on it may no longer land together.
prov="$TMP/prov"; mkdir -p "$prov/fleet/board" "$prov/fleet/state"
head -3 "$SUBSTRATE_REGISTRY" >"$prov/fleet/state/EVAL-REGISTRY.md"
( cd "$prov" && git init -q . && git config user.email t@t && git config user.name t \
  && git add -A && git commit -qm base ) >/dev/null 2>&1
prov_base="$(git -C "$prov" rev-parse HEAD)"
printf '%s\n' '| SelfServed | scope | 2026-07-20 | REJECTED | aligned | this row was appended by the author of the very ticket that cites it, in the same change, with no separate review of the eval | https://example.invalid/eval | — |' >>"$prov/fleet/state/EVAL-REGISTRY.md"
cat >"$prov/fleet/board/SELF.md" <<'TIC'
work_class: money-path
difficulty: 5
owns: src/charon/t.py
substrate: SelfServed — reject — the registry row backing this claim is added by this very change, so the consult is the author agreeing with themselves rather than citing settled work
TIC
( cd "$prov" && git add -A && git commit -qm selfserve ) >/dev/null 2>&1
prov_out="$(RIG_CI_BASE="$prov_base" RIG_CI_HEAD=HEAD python3 -c "
import sys
sys.path.insert(0,'$HERE/../checks')
import substrate_first_gate as g
gate=g.Gate('$prov/fleet/state/EVAL-REGISTRY.md','$prov')
sys.exit(g.cmd_check(gate,['$prov/fleet/board/SELF.md']))" 2>&1)"; prov_rc=$?
if [ "$prov_rc" -ne 0 ] && grep -q 'THIS SAME change adds' <<<"$prov_out"; then
  ok "S3c a registry row added by the SAME change may not be cited [RED]"
else
  bad "S3c self-served registry row passed (rc=$prov_rc)"; printf '%s\n' "$prov_out" | sed 's/^/        /'
fi

# S6-PR — the PR-level assertion: a change that touches code must carry a board ticket.
# Hermetic: a throwaway git repo, never this one.
pr_repo="$TMP/prrepo"; mkdir -p "$pr_repo/fleet/board" "$pr_repo/src"
( cd "$pr_repo" && git init -q . && git config user.email t@t && git config user.name t \
  && echo x >README.md && git add -A && git commit -qm base ) >/dev/null 2>&1
pr_base="$(git -C "$pr_repo" rev-parse HEAD)"
( cd "$pr_repo" && echo 'print(1)' >src/new_thing.py && git add -A && git commit -qm code ) >/dev/null 2>&1
pr_out="$(RIG_CI_BASE="$pr_base" RIG_CI_HEAD=HEAD SUBSTRATE_GATE_ACTIVE= \
          python3 -c "
import os,sys
sys.argv=['x','pr-has-ticket']
sys.path.insert(0,'$HERE/../checks')
import substrate_first_gate as g
gate=g.Gate('$SUBSTRATE_REGISTRY','$pr_repo')
sys.exit(g.cmd_pr_has_ticket(gate))" 2>&1)"; pr_rc=$?
[ "$pr_rc" -ne 0 ] && ok "S6c a change touching code with NO board ticket REDs [rc=$pr_rc]" \
  || { bad "S6c code-with-no-ticket passed"; printf '%s\n' "$pr_out" | sed 's/^/        /'; }
( cd "$pr_repo" && echo 'work_class: money-path' >fleet/board/T.md && git add -A && git commit -qm ticket ) >/dev/null 2>&1
pr_out2="$(RIG_CI_BASE="$pr_base" RIG_CI_HEAD=HEAD python3 -c "
import sys
sys.path.insert(0,'$HERE/../checks')
import substrate_first_gate as g
sys.exit(g.cmd_pr_has_ticket(g.Gate('$SUBSTRATE_REGISTRY','$pr_repo')))" 2>&1)"; pr_rc2=$?
[ "$pr_rc2" -eq 0 ] && ok "S6d the same change WITH a board ticket is green" \
  || { bad "S6d code+ticket false-alarmed"; printf '%s\n' "$pr_out2" | sed 's/^/        /'; }

# G7 — retrofit mode reports and never edits.
before="$(md5sum "$BOARD"/*.md | md5sum)"
bash "$GATE" retrofit "$BOARD" >/dev/null 2>&1
after="$(md5sum "$BOARD"/*.md | md5sum)"
[ "$before" = "$after" ] && ok "G7 retrofit mode edits nothing" || bad "G7 retrofit MUTATED the board"

echo
echo "substrate-first-gate.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
