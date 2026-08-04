#!/usr/bin/env bash
# status-board.test.sh — FAIL-ON-REVERT red-proof for fleet/status-board/generate.sh.
#
# WHAT IS ACTUALLY DEFENDED HERE (and it is not "does the page render")
#   The status board's ONE job is to distinguish three states and never collapse them into two:
#     GREEN     checked AND passing
#     RED       checked AND failing
#     UNPROVEN  we cannot claim it — the check would not run, or nothing has ever shown the check
#               capable of failing, so "it passed" is worthless.
#   The failure this guards is the GREEN LIE, and it is on this project's record twice: 114
#   red-proof suites that are absent from the LITERAL CI_SUITES allowlist and therefore have never
#   executed, and a PASSING check reported as RED for weeks. A page that renders an unknown as
#   green is worse than no page, because the operator would believe it.
#
#   So GREEN-IS-NOT-PROOF applies to this suite too: `generate.sh` exiting 0 and writing a big
#   pretty file proves nothing. Every case below asserts the STATE A SPECIFIC TILE RENDERS under a
#   specific defect, and each one asserts the ABSENCE of PASSING as well as the presence of
#   UNPROVEN — because the whole defect class is "unknown silently became good news".
#
# FAIL-ON-REVERT — five reverts of generate.sh, each VERIFIED to drive this suite RED, with the
# exact assertion that catches it (measured, not assumed — see the note under (c)/(e)):
#   (1) _verdict()'s `rc==0` arm changed to `echo GREEN`, i.e. stop consulting whether the
#       red-proof actually runs in CI -> the exact 114-unenforced-suites lie renders green.
#       Caught by f1 f2 f4 g1 g2 g3 (6 failures). THE LOAD-BEARING REVERT OF THE WHOLE TICKET.
#   (2) _proof() returns 0 when the allowlist cannot be read (fail-OPEN) -> a gate verdict is
#       claimed with no evidence at all. Caught by g1 g2 g3.
#   (3) the `127` arm of _run() deleted -> a source that DOES NOT EXIST is reported inaccurately.
#       Caught by c4 (the reason text), NOT by c2.
#   (4) the `124` arm deleted -> a source that never finished. Caught by d2, not d1.
#   (5) the `[ ! -s "$RUN_OUT" ]` silent-output refusal deleted -> exit 0 having measured nothing,
#       the vacuous-green class. Caught by e3, not e1/e2.
#   WHY THE REASON-TEXT ASSERTIONS ARE THE CATCHERS, and this is worth stating plainly: generate.sh
#   has defence in depth — each tile's parser refuses to invent a number it cannot find, so even
#   with _run's guards removed the tile still lands on UNPROVEN. The state assertions (c2/d1/e1)
#   therefore pass either way and cannot red-proof those three arms; the reason assertions can,
#   because only the guard being reverted can emit that sentence. A suite whose headline assertions
#   pass under the revert is a suite that cannot fail — the same defect this page exists to expose,
#   so it is documented here rather than left as a comfortable assumption.
#
# HERMETIC / OFFLINE / FAST — the conditions for being allowed into CI_SUITES:
#   Every source generate.sh reads is env-overridden to a `printf` stub or a temp fixture file
#   under mktemp -d. The two NETWORK sources are bypassed by their documented offline hooks
#   (SB_PR_FIXTURE, SB_GATEWAY_{STATUS,CONFIG}_JSON), so no `gh`, no `curl`, no gateway and no
#   git remote is ever touched. Nothing outside the temp dir is written. Runtime ~3s.
#   NOT A FIXTURE BYPASS (cf. fleet/checks/fixture-bypass.sh): the overrides feed the SAME
#   _run/_verdict/_proof functions the production run uses. The defect is injected into the
#   SOURCE, never into the logic under test.
#
# Run:  bash fleet/tests/status-board.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GEN="$SRC/status-board/generate.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

[ -f "$GEN" ] || { echo "FAIL: fleet/status-board/generate.sh is missing — nothing to test"; exit 1; }

ROOT="$(mktemp -d)" || { echo "FAIL: mktemp -d"; exit 1; }
trap 'rm -rf "$ROOT" 2>/dev/null || true' EXIT

# ---- fixtures -------------------------------------------------------------------------------
mkdir -p "$ROOT/tests" "$ROOT/board"
# fleet/tests/ stand-in: the suite files must EXIST for _proof to distinguish
# "no proof suite at all" from "a proof suite that never runs in CI".
for s in stranded-work board-correctness gate-integrity graphify-freshness service-watchdog; do
  : >"$ROOT/tests/$s.test.sh"
done
# The CI_SUITES allowlist stand-in. graphify-freshness/service-watchdog are DELIBERATELY absent —
# that mirrors the live rig, where those proofs exist and have never executed.
ALLOW="$ROOT/suites.txt"
printf 'stranded-work.test.sh\nboard-correctness.test.sh\ngate-integrity.test.sh\n' >"$ALLOW"

printf 'priority: 0\n' >"$ROOT/board/AAA.md"
printf 'priority: 2\n' >"$ROOT/board/BBB.md"
printf 'priority: 0\n' >"$ROOT/board/CCC.md.parked"
printf 'svc-a\tprocess\tpgrep:x\tnone\t0\ttrue\towner\n' >"$ROOT/registry.tsv"
printf 'o/r\t1\ttrue\taaa\t"success"\no/r\t2\tfalse\tbbb\t"failure"\n' >"$ROOT/pr.tsv"
cat >"$ROOT/gw-status.json" <<'J'
{"balance":{"p1":{"parked":true},"p2":{"parked":false}},"build_sha":"0123456789abcdef"}
J
cat >"$ROOT/gw-config.json" <<'J'
{"models":{"m1":{},"m2":{}},"unknown_pricing":["m1"],"pools":{"pool1":{}}}
J
cat >"$ROOT/graph.json" <<'J'
{"nodes":[{"id":"a","community":1},{"id":"b","community":1}],"links":[{"source":"a","target":"b"}],"built_at_commit":"deadbeefcafe"}
J

# The stranded-work tile is this suite's PROBE: its stub PASSES (0 findings) and its red-proof
# stranded-work.test.sh IS in the allowlist, so a correct generator renders it PASSING. Every
# defect case below breaks ONLY this tile and asserts it turns UNPROVEN — proving the generator
# distinguishes "cannot claim" from "good news", which is the entire deliverable.
PROBE_LABEL='Pieces of unfinished work that could be lost'
GOOD_STRANDED="printf 'stranded-work: 0 finding(s)\\n'"

# gen <out.html> [VAR=value ...]  — run generate.sh fully stubbed and offline.
gen(){
  local out="$1"; shift
  env \
    SB_OUT="$out" \
    SB_RIG_REPO="$ROOT" \
    SB_PRODUCT_REPO="$ROOT" \
    SB_TIMEOUT="${SB_T:-20}" \
    SB_CI_SUITES_CMD="${CI_CMD:-cat '$ALLOW'}" \
    SB_TESTS_DIR="$ROOT/tests" \
    SB_BOARD_DIR="$ROOT/board" \
    SB_REGISTRY_TSV="$ROOT/registry.tsv" \
    SB_GRAPH_JSON="$ROOT/graph.json" \
    SB_PR_FIXTURE="$ROOT/pr.tsv" \
    SB_GATEWAY_STATUS_JSON="$ROOT/gw-status.json" \
    SB_GATEWAY_CONFIG_JSON="$ROOT/gw-config.json" \
    SB_PRODUCT_GATE_CMD="printf '  [ruff] OK\\n  [mypy] OK\\n'" \
    SB_RIG_GATE_CMD="printf '  RED  2 issue(s)\\n'; exit 1" \
    SB_GATE_INTEGRITY_CMD="printf 'G3 UNPROVEN: x\\nG5 UNENFORCED-PROOF: 4 suites\\ngate-integrity: 6 finding(s)\\n'" \
    SB_STRANDED_CMD="${STRANDED_CMD:-$GOOD_STRANDED}" \
    SB_FRESHNESS_CMD="printf '  repo | FRESH | fine\\n'" \
    SB_LIVENESS_CMD="printf '  ok    svc-a — alive (pgrep:x)\\n== watchdog: GREEN ==\\n'" \
    "$@" \
    bash "$GEN" >"$out.log" 2>&1
}

# tile_state <html> <label> -> the chip word rendered on that tile (PASSING|FAILING|UNPROVEN|?)
# Reads the tile block that carries the label, so it cannot accidentally match a neighbour.
tile_state(){
  python3 - "$1" "$2" <<'PY'
import re, sys
h = open(sys.argv[1], encoding="utf-8", errors="replace").read()
want = sys.argv[2]
for block in h.split('<article class="tile')[1:]:
    block = block.split("</article>")[0]
    if want in block:
        m = re.search(r'PASSING|FAILING|UNPROVEN|COUNTED', block)
        print(m.group(0) if m else "NO-CHIP"); break
else:
    print("NO-SUCH-TILE")
PY
}
count_chip(){ grep -o ">$2<" "$1" 2>/dev/null | wc -l | tr -d ' '; }

echo "== (a) HAPPY PATH: a fully-stubbed run exits 0 and writes real, non-empty HTML =="
gen "$ROOT/a.html"; rc=$?
check "a1 generate.sh exit 0" "$rc" "0"
[ -s "$ROOT/a.html" ] && ok "a2 board.html written and non-empty" || bad "a2 board.html written and non-empty"
grep -q '<title>' "$ROOT/a.html" && ok "a3 has a <title>" || bad "a3 has a <title>"
grep -q '<style>' "$ROOT/a.html" && ok "a4 CSS is inlined in a <style> block" || bad "a4 CSS is inlined in a <style> block"
grep -q '<article class="tile' "$ROOT/a.html" && ok "a5 renders tiles" || bad "a5 renders tiles"
o="$(grep -c '<article class="tile' "$ROOT/a.html")"; c="$(grep -c '</article>' "$ROOT/a.html")"
check "a6 every tile element is closed" "$o" "$c"
grep -q 'prefers-color-scheme:dark' "$ROOT/a.html" && ok "a7 has a dark-theme branch" || bad "a7 has a dark-theme branch"
grep -q 'data-theme="dark"' "$ROOT/a.html" && ok "a8 honours an explicit theme stamp" || bad "a8 honours an explicit theme stamp"
# "valid HTML" as a real assertion, not a vibe: every non-void element opens and closes in order.
# A page that renders but is structurally broken can swallow a whole tile inside a stray element,
# which is a silent way to lose a RED.
python3 - "$ROOT/a.html" <<'PY' && ok "a9 HTML is structurally well-formed (all elements balanced and nested)" \
                              || bad "a9 HTML is NOT structurally well-formed"
from html.parser import HTMLParser
import sys
VOID = {"meta","br","hr","img","input","link","source","area","base","col","embed","param","track","wbr"}
class V(HTMLParser):
    def __init__(self):
        super().__init__(); self.stack=[]; self.err=[]
    def handle_starttag(self, t, a):
        if t not in VOID: self.stack.append(t)
    def handle_endtag(self, t):
        if t in VOID: return
        if not self.stack: self.err.append("stray </%s>" % t)
        elif self.stack[-1] != t: self.err.append("</%s> closes <%s>" % (t, self.stack[-1]))
        else: self.stack.pop()
v = V(); v.feed(open(sys.argv[1], encoding="utf-8", errors="replace").read())
if v.stack or v.err:
    print("unclosed=%s errors=%s" % (v.stack[:5], v.err[:5]), file=sys.stderr); sys.exit(1)
sys.exit(0)
PY

echo "== (b) SELF-CONTAINED + SNAPSHOT-STAMPED: opens from disk, never claims to be live =="
# A page that reaches the network is not a snapshot of anything, and a page that omits its
# timestamp/shas invites being read as live.
grep -qiE '<script|\ssrc=|<link|@import' "$ROOT/a.html" \
  && bad "b1 no scripts / external references" || ok "b1 no scripts / external references"
grep -qiE '(href|src)="https?:' "$ROOT/a.html" \
  && bad "b2 no remote resource is fetched" || ok "b2 no remote resource is fetched"
grep -qi 'Snapshot' "$ROOT/a.html" && ok "b3 labelled a SNAPSHOT" || bad "b3 labelled a SNAPSHOT"
grep -qE 'measured <b>once</b>' "$ROOT/a.html" && ok "b4 states plainly that it does not refresh" || bad "b4 states plainly that it does not refresh"
grep -q 'Build-rig repo at' "$ROOT/a.html" && grep -q 'Product repo at' "$ROOT/a.html" \
  && ok "b5 stamps BOTH repo HEADs" || bad "b5 stamps BOTH repo HEADs"
grep -qE '[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC' "$ROOT/a.html" \
  && ok "b6 stamps the generation time" || bad "b6 stamps the generation time"
grep -q 'What this page cannot tell you' "$ROOT/a.html" \
  && ok "b7 carries the 'what this page cannot tell you' section" || bad "b7 carries that section"
# POSITIVE CONTROL for every case below: with a working, CI-enforced source the probe IS green.
# Without this, "renders UNPROVEN" could be trivially satisfied by a generator that greys out
# everything, which would be just as useless as one that greens everything.
check "b8 POSITIVE CONTROL — probe tile is PASSING when its source works and its proof runs in CI" \
  "$(tile_state "$ROOT/a.html" "$PROBE_LABEL")" "PASSING"
BASE_PASSING="$(count_chip "$ROOT/a.html" PASSING)"

echo "== (c) FAIL-ON-REVERT: a source that DOES NOT EXIST renders UNPROVEN, never green =="
# The literal requirement: break the source, then restore it. rc 127 must not become a verdict.
STRANDED_CMD="bash '$ROOT/definitely-not-a-real-script.sh'" gen "$ROOT/c.html"; rc=$?
check "c1 generate.sh still exits 0 (a reporter reports; it does not die on a bad source)" "$rc" "0"
st="$(tile_state "$ROOT/c.html" "$PROBE_LABEL")"
check "c2 broken source -> tile renders UNPROVEN" "$st" "UNPROVEN"
[ "$st" = "PASSING" ] && bad "c3 broken source must NEVER render PASSING" || ok "c3 broken source did not render PASSING"
grep -q 'was not found' "$ROOT/c.html" && ok "c4 the page names the actual failure (file not found)" \
                                       || bad "c4 the page names the actual failure (file not found)"
python3 - "$ROOT/c.html" "$PROBE_LABEL" <<'PY' && ok "c5 the broken tile is listed in 'what this page cannot tell you'" \
                                              || bad "c5 the broken tile is listed in 'what this page cannot tell you'"
import sys
h = open(sys.argv[1], encoding="utf-8", errors="replace").read()
sec = h.split("What this page cannot tell you", 1)[-1]
sys.exit(0 if sys.argv[2] in sec else 1)
PY
# RESTORE: the same tile must go back to PASSING, proving c2 was caused by the break and not by
# some unrelated permanent greying.
gen "$ROOT/c2.html"
check "c6 RESTORED source -> tile is PASSING again" "$(tile_state "$ROOT/c2.html" "$PROBE_LABEL")" "PASSING"

echo "== (d) FAIL-ON-REVERT: a source that never FINISHES renders UNPROVEN, never green =="
SB_T=1 STRANDED_CMD="sleep 30" gen "$ROOT/d.html"
st="$(tile_state "$ROOT/d.html" "$PROBE_LABEL")"
check "d1 timed-out source -> UNPROVEN" "$st" "UNPROVEN"
grep -q 'did not finish within' "$ROOT/d.html" && ok "d2 the page says it timed out" || bad "d2 the page says it timed out"

echo "== (e) FAIL-ON-REVERT: a SILENT source (exit 0, no output) renders UNPROVEN, never green =="
# The vacuous-green class: exit 0 having measured nothing is the most dangerous input of all,
# because it looks exactly like success.
STRANDED_CMD="true" gen "$ROOT/e.html"
st="$(tile_state "$ROOT/e.html" "$PROBE_LABEL")"
check "e1 silent source -> UNPROVEN" "$st" "UNPROVEN"
[ "$st" = "PASSING" ] && bad "e2 a source that printed nothing must never render PASSING" \
                       || ok "e2 a source that printed nothing did not render PASSING"
# e3 IS the revert-catcher, and e1/e2 are not. Measured: with the silent-output refusal deleted,
# _run returns success on an empty result and the tile STILL renders UNPROVEN — because the tile's
# own parser refuses to invent a number it cannot find. That defence-in-depth is welcome, but it
# means e1/e2 pass either way, so on their own they are a test that cannot fail. Asserting the
# REASON is what pins the guard: only the refusal in _run can produce this sentence.
grep -q 'printed nothing, so there is no measurement' "$ROOT/e.html" \
  && ok "e3 the page attributes it to an empty result, not to a parsing accident" \
  || bad "e3 the page does NOT attribute it to an empty result (the silent-output refusal in _run is gone)"

echo "== (f) THE HONESTY RULE: a PASSING check whose red-proof never runs in CI is UNPROVEN =="
# THE LOAD-BEARING CASE. The source succeeds. The check passes. The ONLY thing wrong is that its
# red-proof suite is not in the CI_SUITES allowlist, so nothing has ever shown the check capable of
# failing. That must render UNPROVEN. This is the 114-unenforced-suites defect, tile-sized.
printf 'board-correctness.test.sh\ngate-integrity.test.sh\n' >"$ROOT/suites-noproof.txt"
CI_CMD="cat '$ROOT/suites-noproof.txt'" gen "$ROOT/f.html"
st="$(tile_state "$ROOT/f.html" "$PROBE_LABEL")"
check "f1 passing check + unenforced red-proof -> UNPROVEN" "$st" "UNPROVEN"
[ "$st" = "PASSING" ] && bad "f2 an unenforced red-proof must NEVER render PASSING" \
                       || ok "f2 an unenforced red-proof did not render PASSING"
grep -q 'never executed in CI' "$ROOT/f.html" \
  && ok "f3 the page explains that the proof never executed in CI" \
  || bad "f3 the page explains that the proof never executed in CI"
# And the tile that has NO proof suite at all must also be UNPROVEN, not green.
rm -f "$ROOT/tests/stranded-work.test.sh"
gen "$ROOT/f2.html"
check "f4 no red-proof suite exists at all -> UNPROVEN" "$(tile_state "$ROOT/f2.html" "$PROBE_LABEL")" "UNPROVEN"
grep -q 'NO red-proof suite exists' "$ROOT/f2.html" && ok "f5 the page says no proof exists" || bad "f5 the page says no proof exists"
: >"$ROOT/tests/stranded-work.test.sh"

echo "== (g) FAIL-CLOSED: if the CI allowlist itself cannot be read, NOTHING renders green =="
# Uncertainty about the proofs must collapse every pass to UNPROVEN, never the other way.
CI_CMD="bash '$ROOT/no-such-allowlist.sh'" gen "$ROOT/g.html"
check "g1 unreadable allowlist -> probe tile UNPROVEN" "$(tile_state "$ROOT/g.html" "$PROBE_LABEL")" "UNPROVEN"
G_PASSING="$(count_chip "$ROOT/g.html" PASSING)"
[ "$G_PASSING" -lt "${BASE_PASSING:-0}" ] \
  && ok "g2 unreadable allowlist collapses passing tiles ($BASE_PASSING -> $G_PASSING)" \
  || bad "g2 unreadable allowlist did NOT collapse passing tiles ($BASE_PASSING -> $G_PASSING) — fail-open"
# The ONLY tiles allowed to stay green without the allowlist are the DIRECT ones (a bare read of a
# primary field, with no gate logic that could be inert). Anything else going green here means a
# gate verdict was claimed with no evidence that the gate can fail — the exact fail-open defect.
# This is also what stops `_proof_direct` from becoming a rubber stamp: a tile can only take the
# exemption by SAYING so on the page, where this assertion can see it.
python3 - "$ROOT/g.html" <<'PY' && ok "g3 every still-passing tile is a DIRECT primary-field read, not a gate verdict" \
                                || bad "g3 a GATE-backed tile went green while the allowlist was unreadable (fail-open)"
import sys
h = open(sys.argv[1], encoding="utf-8", errors="replace").read()
for b in h.split('<article class="tile')[1:]:
    body = b.split("</article>")[0]
    if "PASSING" in body and "DIRECT read of a primary field" not in body:
        sys.exit(1)
sys.exit(0)
PY
grep -q 'CI_SUITES allowlist itself could not be read' "$ROOT/g.html" \
  && ok "g4 the page names the allowlist as the thing that failed" || bad "g4 the page names the allowlist failure"
# Sanity: the baseline run DID have passing tiles, so g2 measures a real collapse, not a vacuous 0.
[ "${BASE_PASSING:-0}" -gt 0 ] && ok "g5 baseline had $BASE_PASSING passing tile(s), so g2 is not vacuous" \
                                || bad "g5 baseline had NO passing tiles — g2 is vacuous and proves nothing"

echo "== (i) the DIRECT exemption is itself red-proofed: the numbers match the fixture exactly =="
# `_proof_direct` lets a tile go green without a CI-enforced suite, on the grounds that it merely
# reads a primary field. That claim is only acceptable if the arithmetic is checked, otherwise the
# exemption is a blank cheque. The fixture is 2 change-requests (1 draft, 1 failing), 2 suppliers
# (1 parked) and 2 models (1 unpriced) — so every one of these must read "1 of 2".
i_n=0
for lbl in "Change-requests marked" "Change-requests whose automatic checks are failing" \
           "AI suppliers switched off" "Models we cannot put a price on"; do
  i_n=$((i_n+1))
  n="$(python3 - "$ROOT/a.html" "$lbl" <<'PY'
import re, sys
h = open(sys.argv[1], encoding="utf-8", errors="replace").read()
for b in h.split('<article class="tile')[1:]:
    body = b.split("</article>")[0]
    if sys.argv[2] in body:
        m = re.search(r'<p class="big">([^<]*)</p>', body)
        print(m.group(1) if m else "NO-NUMBER"); break
else:
    print("NO-SUCH-TILE")
PY
)"
  check "i$i_n '$lbl' reads the fixture exactly" "$n" "1 of 2"
done

echo "== (h) COUNTED is a headcount, never a verdict, and never coloured as passing =="
# The fourth chip exists so inventory numbers cannot masquerade as good news.
grep -q 'COUNTED' "$ROOT/a.html" && ok "h1 inventory tiles are rendered" || bad "h1 inventory tiles are rendered"
python3 - "$ROOT/a.html" <<'PY' && ok "h2 no COUNTED tile carries the passing (good) colour class" \
                                || bad "h2 a COUNTED tile carries the passing colour class"
import sys
h = open(sys.argv[1], encoding="utf-8", errors="replace").read()
for b in h.split('<article class="tile')[1:]:
    head, _, rest = b.partition('>')
    body = rest.split("</article>")[0]
    if "COUNTED" in body and "s-good" in head:
        sys.exit(1)
sys.exit(0)
PY
grep -q 'Counted is not the same as passing' "$ROOT/a.html" \
  && ok "h3 the legend states plainly that COUNTED is not PASSING" || bad "h3 the legend states that"
grep -q 'There are three verdicts, never two' "$ROOT/a.html" \
  && ok "h4 the legend states the three-state rule" || bad "h4 the legend states the three-state rule"

echo "== (j) no UNPROVEN tile shows a NUMBER as its headline — grey is not a way to publish a figure =="
# The subtle version of the green lie: a tile that renders UNPROVEN but headlines a big "0". A
# non-coder reads the number, not the chip. Measured on the live rig: the code-map freshness check
# reports 0 stale maps while its red-proof has never run, so "0" is precisely the figure this page
# must refuse to headline. FAIL-ON-REVERT: drop the `"unknown" if state == "UNPROVEN"` substitution
# in tile_html and every such tile headlines its raw figure again -> j1 goes RED.
j_bad=""
for f in a c d e f f2 g; do
  [ -s "$ROOT/$f.html" ] || continue
  python3 - "$ROOT/$f.html" <<'PY' || j_bad="$j_bad $f.html"
import re, sys
h = open(sys.argv[1], encoding="utf-8", errors="replace").read()
for b in h.split('<article class="tile')[1:]:
    body = b.split("</article>")[0]
    if "UNPROVEN" not in body:
        continue
    m = re.search(r'<p class="big[^"]*">([^<]*)</p>', body)
    if m and any(ch.isdigit() for ch in m.group(1)):
        sys.exit(1)
sys.exit(0)
PY
done
[ -z "$j_bad" ] && ok "j1 no UNPROVEN tile headlines a number, across every page this suite rendered" \
                || bad "j1 an UNPROVEN tile headlines a raw number in:$j_bad"
grep -q 'but this page will not report that as a result' "$ROOT/a.html" \
  && ok "j2 a figure an unproven check DID produce is demoted into the reason, not hidden" \
  || bad "j2 the measured figure was dropped entirely instead of being demoted into the reason"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL STATUS-BOARD TESTS PASS"
