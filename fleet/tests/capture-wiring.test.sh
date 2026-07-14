#!/usr/bin/env bash
# capture-wiring.test.sh — FAIL-ON-REVERT tests for the run/land -> scorecard
# capture wiring (charon-run.sh success/fail hooks + done.sh FINAL land hook).
#
# Both sites only ENQUEUE into the bench-grader-owned spool (via
# capture/enqueue-capture.sh) -- they NEVER touch model-scorecard.tsv, which
# stays out of reach for the `stack` user (see fleet/ADR-BENCH-OOB-GRADING.md).
# Hermetic: CAPTURE_SPOOL_DIR is redirected to a tmp maildrop for every case,
# and `opencode` is stubbed on PATH so no network/gateway call ever happens.
#
# Run: bash fleet/tests/capture-wiring.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

req_json_for() {  # req_json_for <spool_req_dir> <ref-substring> -> path of the one match (last if many)
  grep -l "\"ref\": \"$2\"" "$1"/*.json 2>/dev/null | tail -n1
}
field() { python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" "$1" "$2"; }

# ---- stub opencode on PATH: exit 0 (success) or 1 (non-limit failure) ----
BIN="$(mktemp -d)"
cat > "$BIN/opencode" <<'EOF'
#!/usr/bin/env bash
case "$OPENCODE_STUB_MODE" in
  fail) echo "boom: something went wrong" >&2; exit 1 ;;
  *)    echo "ok" ; exit 0 ;;
esac
EOF
chmod +x "$BIN/opencode"
export PATH="$BIN:$PATH"

# ============================ charon-run.sh SUCCESS ============================
echo "== charon-run.sh: success -> PROVISIONAL capture + model-used record =="
d="$(mktemp -d)"
cp -r "$SRC/capture" "$d/"
cp "$SRC/charon-run.sh" "$d/"
spool="$d/spool"; mkdir -p "$spool"
cwd="$(mktemp -d)"; brief="$d/brief.md"; echo "do the thing" > "$brief"; outlog="$d/out.txt"

rc=0
CAPTURE_SPOOL_DIR="$spool" CHARON_JOB_REF="TICK-CAP" CHARON_JOB_WORK_CLASS="bugfix" \
  OPENCODE_STUB_MODE=ok bash "$d/charon-run.sh" "$cwd" "$outlog" "$brief" my-model >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && ok "run exits 0 on stub success" || bad "run exits 0 on stub success (rc=$rc)"

f="$(req_json_for "$spool" "TICK-CAP")"
[ -n "$f" ] && ok "success enqueues a capture request" || bad "success enqueues a capture request"
if [ -n "$f" ]; then
  [ "$(field "$f" claimed_result)" = "SUCCESS" ] && ok "success row claimed_result=SUCCESS" || bad "success row claimed_result=SUCCESS"
  [ "$(field "$f" stage)" = "provisional" ] && ok "success row is PROVISIONAL (no verdict yet)" || bad "success row is PROVISIONAL (no verdict yet)"
fi
[ -f "$d/state/model-used/TICK-CAP" ] && ok "model-used record written for done.sh pairing" \
  || bad "model-used record written for done.sh pairing"
[ "$(cat "$d/state/model-used/TICK-CAP" 2>/dev/null)" = "my-model" ] && ok "model-used record names the winning model" \
  || bad "model-used record names the winning model"
rm -rf "$d" "$cwd"

# ============================ charon-run.sh non-limit FAILURE ============================
echo "== charon-run.sh: non-limit failure -> FINAL BLOCK/fail capture =="
d="$(mktemp -d)"
cp -r "$SRC/capture" "$d/"
cp "$SRC/charon-run.sh" "$d/"
spool="$d/spool"; mkdir -p "$spool"
cwd="$(mktemp -d)"; brief="$d/brief.md"; echo "do the thing" > "$brief"; outlog="$d/out.txt"

rc=0
CAPTURE_SPOOL_DIR="$spool" CHARON_JOB_REF="TICK-FAIL" CHARON_JOB_WORK_CLASS="bugfix" \
  OPENCODE_STUB_MODE=fail bash "$d/charon-run.sh" "$cwd" "$outlog" "$brief" my-model >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 0 ] && ok "run exits non-zero on stub hard failure (all models exhausted)" \
                || bad "run exits non-zero on stub hard failure"

f="$(req_json_for "$spool" "TICK-FAIL")"
[ -n "$f" ] && ok "non-limit failure enqueues a capture request" || bad "non-limit failure enqueues a capture request"
if [ -n "$f" ]; then
  [ "$(field "$f" claimed_result)" = "FAIL" ] && ok "failure row claimed_result=FAIL" || bad "failure row claimed_result=FAIL"
  [ "$(field "$f" actual_verdict)" = "BLOCK" ] && ok "failure row is FINAL actual_verdict=BLOCK (self-evident, no review needed)" \
                                              || bad "failure row is FINAL actual_verdict=BLOCK"
  [ "$(field "$f" actual_gate)" = "fail" ] && ok "failure row actual_gate=fail" || bad "failure row actual_gate=fail"
  [ "$(field "$f" stage)" = "active" ] && ok "failure row is stage=active (counts immediately)" \
                                        || bad "failure row is stage=active"
fi
rm -rf "$d" "$cwd"

# ============================ charon-run.sh limit-failover ============================
echo "== charon-run.sh: provider/session LIMIT -> NO capture row (provider fault, not model quality) =="
d="$(mktemp -d)"
cp -r "$SRC/capture" "$d/"
cp "$SRC/charon-run.sh" "$d/"
spool="$d/spool"; mkdir -p "$spool"
cwd="$(mktemp -d)"; brief="$d/brief.md"; echo "do the thing" > "$brief"; outlog="$d/out.txt"

cat > "$BIN/opencode" <<'EOF'
#!/usr/bin/env bash
echo "429 rate limit exceeded" >&2
exit 1
EOF
chmod +x "$BIN/opencode"

CAPTURE_SPOOL_DIR="$spool" CHARON_JOB_REF="TICK-LIMIT" CHARON_JOB_WORK_CLASS="bugfix" \
  bash "$d/charon-run.sh" "$cwd" "$outlog" "$brief" my-model >/dev/null 2>&1 || true
f="$(req_json_for "$spool" "TICK-LIMIT")"
[ -z "$f" ] && ok "limit-failover does NOT enqueue a scorecard row" || bad "limit-failover does NOT enqueue a scorecard row (found $f)"
rm -rf "$d" "$cwd"

# ============================ FLAW-2 (2026-07-13): provider/local/infra faults ============================
# BEFORE the fix, ANY non-limit nonzero rc (gateway 5xx, connection reset/
# refused, context-deadline, sqlite db-lock, the `timeout 1800` wrapper firing
# rc=124, an opaque rc=3) wrongly enqueued a model BLOCK. Each case below MUST
# enqueue NOTHING -- only a genuine model-attributable failure still BLOCKs
# (covered by the non-limit FAILURE block above, unchanged).
run_infra_fault_case() {  # run_infra_fault_case <label> <ref> <stub-body>
  local label="$1" ref="$2" stub_body="$3"
  local d spool cwd brief outlog
  d="$(mktemp -d)"; cp -r "$SRC/capture" "$d/"; cp "$SRC/charon-run.sh" "$d/"
  spool="$d/spool"; mkdir -p "$spool"
  cwd="$(mktemp -d)"; brief="$d/brief.md"; echo "do the thing" > "$brief"; outlog="$d/out.txt"
  printf '#!/usr/bin/env bash\n%s\n' "$stub_body" > "$BIN/opencode"
  chmod +x "$BIN/opencode"
  CAPTURE_SPOOL_DIR="$spool" CHARON_JOB_REF="$ref" CHARON_JOB_WORK_CLASS="bugfix" \
    bash "$d/charon-run.sh" "$cwd" "$outlog" "$brief" my-model >/dev/null 2>&1 || true
  local f; f="$(req_json_for "$spool" "$ref")"
  [ -z "$f" ] && ok "$label -> NO capture row (infra/provider fault, not model quality)" \
             || bad "$label -> NO capture row (found $f)"
  rm -rf "$d" "$cwd"
}
echo "== charon-run.sh: provider/local/infra faults -> NO capture row (FLAW-2 fix) =="
run_infra_fault_case "gateway 502" "TICK-INFRA-502" 'echo "502 Bad Gateway from upstream" >&2; exit 1'
run_infra_fault_case "connection refused" "TICK-INFRA-CONNREF" 'echo "Error: connect ECONNREFUSED 127.0.0.1:8080" >&2; exit 1'
run_infra_fault_case "connection reset" "TICK-INFRA-CONNRST" 'echo "read: connection reset by peer" >&2; exit 1'
run_infra_fault_case "context deadline exceeded" "TICK-INFRA-CTXDL" 'echo "context deadline exceeded" >&2; exit 1'
run_infra_fault_case "sqlite database is locked" "TICK-INFRA-DBLOCK" 'echo "Error: database is locked" >&2; exit 1'
run_infra_fault_case "timeout kill (rc=124)" "TICK-INFRA-TIMEOUT" 'echo "hanging..." >&2; exit 124'
run_infra_fault_case "opaque rc=3 (phi-4-style)" "TICK-INFRA-RC3" 'echo "unexpected failure" >&2; exit 3'

echo "== charon-run.sh: a genuine non-infra model failure still enqueues BLOCK (unchanged) =="
d="$(mktemp -d)"; cp -r "$SRC/capture" "$d/"; cp "$SRC/charon-run.sh" "$d/"
spool="$d/spool"; mkdir -p "$spool"
cwd="$(mktemp -d)"; brief="$d/brief.md"; echo "do the thing" > "$brief"; outlog="$d/out.txt"
cat > "$BIN/opencode" <<'EOF'
#!/usr/bin/env bash
echo "assertion failed: test_foo expected 1 got 2" >&2
exit 1
EOF
chmod +x "$BIN/opencode"
CAPTURE_SPOOL_DIR="$spool" CHARON_JOB_REF="TICK-MODELFAULT" CHARON_JOB_WORK_CLASS="bugfix" \
  bash "$d/charon-run.sh" "$cwd" "$outlog" "$brief" my-model >/dev/null 2>&1 || true
f="$(req_json_for "$spool" "TICK-MODELFAULT")"
[ -n "$f" ] && ok "genuine model failure still enqueues a capture request" || bad "genuine model failure still enqueues a capture request"
if [ -n "$f" ]; then
  [ "$(field "$f" actual_verdict)" = "BLOCK" ] && ok "genuine model failure row is actual_verdict=BLOCK" \
                                                || bad "genuine model failure row is actual_verdict=BLOCK"
fi
rm -rf "$d" "$cwd"

rm -rf "$BIN"

# ============================ done.sh FINAL land capture ============================
echo "== done.sh: verified close -> FINAL MERGE/pass capture paired with model-used =="
d="$(mktemp -d)"
cp "$SRC/done.sh" "$SRC/retire-done.sh" "$SRC/leak-guard.sh" "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$d/"
cp -r "$SRC/capture" "$d/"
mkdir -p "$d/board/archive" "$d/state/done" "$d/state/submitted" "$d/state/claims" "$d/state/needs-push" "$d/state/model-used"
printf 'tier: economy\nbranch: feat/g\nowns: src/present.py\nwork_class: bugfix\n' > "$d/board/TICK-CAP.md"
echo "my-model" > "$d/state/model-used/TICK-CAP"
spool="$d/spool"; mkdir -p "$spool"

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
P="$(mktemp -d)"; git -C "$P" init -q
mkdir -p "$P/src"; echo x > "$P/src/present.py"; git -C "$P" add -A; git -C "$P" commit -q -m base
GOODSHA="$(git -C "$P" rev-parse HEAD)"
git -C "$P" update-ref refs/remotes/origin/master "$GOODSHA"

rc=0
CAPTURE_SPOOL_DIR="$spool" DONE_CHARON_REPO="$P" \
  bash "$d/done.sh" TICK-CAP --merged-sha "$GOODSHA" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && ok "done.sh accepts the verified close" || bad "done.sh accepts the verified close (rc=$rc)"

f="$(req_json_for "$spool" "TICK-CAP")"
[ -n "$f" ] && ok "verified close enqueues a FINAL capture request" || bad "verified close enqueues a FINAL capture request"
if [ -n "$f" ]; then
  [ "$(field "$f" model)" = "my-model" ] && ok "land capture names the model that did the work" \
                                          || bad "land capture names the model that did the work"
  [ "$(field "$f" actual_verdict)" = "MERGE" ] && ok "land capture is actual_verdict=MERGE" || bad "land capture is actual_verdict=MERGE"
  [ "$(field "$f" actual_gate)" = "pass" ] && ok "land capture is actual_gate=pass" || bad "land capture is actual_gate=pass"
  [ "$(field "$f" work_class)" = "bugfix" ] && ok "land capture carries the ticket's work_class" \
                                             || bad "land capture carries the ticket's work_class"
fi
rm -rf "$d" "$P"

# ============================ FLAW-1 (2026-07-13): distinct filenames ============================
# The PROVISIONAL and FINAL for one lifetime deliberately share the SAME
# run_id (for grader-daemon.py's _handle_capture pairing) but MUST land on
# DIFFERENT spool filenames -- grader-daemon.py's _scan_requests dedups by
# FILENAME, so a filename collision would silently swallow the FINAL and the
# provisional's success would never reach the ledger.
echo "== enqueue-capture.sh: PROVISIONAL and FINAL for one run_id use DISTINCT filenames =="
spool="$(mktemp -d)"
CAPTURE_SPOOL_DIR="$spool" "$SRC/capture/enqueue-capture.sh" --model my-model --claimed-result SUCCESS \
  --ref FLAW1-FILENAME --stage provisional >/dev/null 2>&1
CAPTURE_SPOOL_DIR="$spool" "$SRC/capture/enqueue-capture.sh" --model my-model --claimed-result SUCCESS \
  --ref FLAW1-FILENAME --stage active --actual-verdict MERGE --actual-gate pass \
  --score 100 --evidence "test" >/dev/null 2>&1
n="$(find "$spool" -maxdepth 1 -name '*.json' | wc -l)"
[ "$n" -eq 2 ] && ok "provisional + FINAL (same run_id) wrote 2 DISTINCT spool files" \
              || bad "REVERT DETECTED: provisional + FINAL collided onto $n file(s), expected 2"
run_ids="$(python3 -c "
import json,glob
for f in glob.glob('$spool'+'/*.json'):
    print(json.load(open(f)).get('run_id'))
" | sort -u)"
n_run_ids="$(printf '%s\n' "$run_ids" | grep -c .)"
[ "$n_run_ids" -eq 1 ] && ok "both files carry the SAME run_id (pairing key stays stable)" \
                        || bad "both files carry the SAME run_id (got: $run_ids)"
rm -rf "$spool"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL CAPTURE-WIRING TESTS PASS"
