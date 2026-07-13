#!/usr/bin/env bash
# test_preflight_runner.sh — FAIL-ON-REVERT tests for fleet/benchmark/preflight.sh
# (PREFLIGHT Chunk C, the MODEL-PREFLIGHT runner). Design of record:
# fleet/state/PREFLIGHT-DESIGN-V2.md §3 (validity plan) + §4 Chunk C.
#
# Fully hermetic: a stub grader-daemon (a tiny python3 spool watcher, NOT the
# real fleet/benchmark/grader-daemon.py / bench-grader substrate) and a stub
# model command are wired in via env overrides. No live network, no real
# opencode/gateway call, no dependency on the real deployed $KEYS graders.
#
# Covers:
#   (a) N-run aggregation: a scripted PASS/PASS/FAIL sequence for one task
#       yields pass-rate 2/3 -> task PASS; a scripted FAIL/FAIL/PASS sequence
#       for another yields 1/3 -> task FAIL. Proves the runner reads the
#       daemon's res/ verdicts and aggregates per-task pass-RATE correctly,
#       not a single bit.
#   (b) THE DISGUISE INVARIANT: one fixture deliberately embeds its own
#       manifest.tsv/traps.tsv (simulating a leak-risk source dir). Every
#       session worktree the runner creates for it must NEVER contain those
#       filenames, while it MUST contain PROMPT.md. Deleting
#       preflight.sh's copy_session_files denylist loop flips this RED.
#   (c) FAIL-LOUD, never-assume-pass: one task's grader-key has no scripted
#       answer at all (the stub daemon never responds for it) -> that task's
#       pass count must be 0/N (every run recorded FAIL, never silently
#       treated as a pass), and the daemon-unreachable message must appear
#       on stderr.
#   (d) Fully-unreachable daemon (spool req dir does not exist at all) ->
#       the WHOLE battery refuses to start: exit code 2, loud stderr, before
#       ever touching the model command.
#
# Run:  bash fleet/tests/test_preflight_runner.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"           # .../fleet
RUNNER="$SRC/benchmark/preflight.sh"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }
contains(){ case "$2" in *"$3"*) ok "$1" ;; *) bad "$1 (expected haystack to contain '$3')" ;; esac; }
not_contains(){ case "$2" in *"$3"*) bad "$1 (expected haystack to NOT contain '$3')" ;; *) ok "$1" ;; esac; }

[ -x "$RUNNER" ] || { echo "FATAL: runner not found/executable: $RUNNER" >&2; exit 1; }

WORK="$(mktemp -d)"
DAEMON_PID=""
cleanup(){
  [ -n "$DAEMON_PID" ] && kill "$DAEMON_PID" >/dev/null 2>&1
  rm -rf "$WORK"
}
trap cleanup EXIT

# ── build a hermetic task registry (mirrors manifest.tsv's real schema) ─────
TASKS_DIR="$WORK/tasks"
mkdir -p "$TASKS_DIR/fixture-a" "$TASKS_DIR/fixture-b" "$TASKS_DIR/fixture-c"

cat > "$TASKS_DIR/manifest.tsv" <<'EOF'
# test manifest — mirrors the real preflight-tasks/manifest.tsv schema
task_id	mode	grader_key	expected_artifact
TA	modeA	fixture-a	artifact A
TB	modeB	fixture-b	artifact B
TC	modeC	fixture-c	artifact C (grader-daemon never answers this one)
T99	crosscut	*	cross-cutting rule, no standalone fixture (T13/T14 shape)
EOF

echo "Task A prompt — ordinary disguised ticket text." > "$TASKS_DIR/fixture-a/PROMPT.md"
echo "print('seed code A')" > "$TASKS_DIR/fixture-a/code.py"
# DELIBERATE leak-risk plant: this fixture embeds copies of the registry
# files themselves. If the runner's denylist filter is ever reverted, these
# WILL show up in every session worktree copied from this fixture — that is
# exactly what check (b) below asserts never happens.
echo "task_id	mode	grader_key	expected_artifact" > "$TASKS_DIR/fixture-a/manifest.tsv"
echo "grader_key	trap_type	marker" > "$TASKS_DIR/fixture-a/traps.tsv"

echo "Task B prompt — ordinary disguised ticket text." > "$TASKS_DIR/fixture-b/PROMPT.md"
echo "print('seed code B')" > "$TASKS_DIR/fixture-b/code.py"

echo "Task C prompt — ordinary disguised ticket text." > "$TASKS_DIR/fixture-c/PROMPT.md"
echo "print('seed code C')" > "$TASKS_DIR/fixture-c/code.py"

# ── stub model command: records that it was invoked, never touches network ──
MODEL_CMD="$WORK/stub-model.sh"
MODEL_LOG="$WORK/model-invocations.log"
: > "$MODEL_LOG"
cat > "$MODEL_CMD" <<EOF
#!/usr/bin/env bash
# stub-model.sh <cwd> <outlog> <brief> <model> — mocks charon-run.sh's contract.
echo "\$1|\$3|\$4" >> "$MODEL_LOG"
echo "stub model ran" >> "\$2"
exit 0
EOF
chmod +x "$MODEL_CMD"

# ── stub grader-daemon: watches req/, answers from a scripted sequence ──────
REQ_DIR="$WORK/spool/req"; RES_DIR="$WORK/spool/res"; SEQ_DIR="$WORK/seq"
mkdir -p "$REQ_DIR" "$RES_DIR" "$SEQ_DIR"
printf 'pass\npass\nfail\n' > "$SEQ_DIR/fixture-a.seq"   # -> 2/3 PASS
printf 'fail\nfail\npass\n' > "$SEQ_DIR/fixture-b.seq"   # -> 1/3 FAIL
# deliberately NO fixture-c.seq -> stub daemon never answers fixture-c at all

STUB_DAEMON="$WORK/stub-daemon.py"
cat > "$STUB_DAEMON" <<'PYEOF'
import json, sys, time
from pathlib import Path

req_dir, res_dir, seq_dir = (Path(a) for a in sys.argv[1:4])
seen = set()
pos = {}

def next_verdict(unit_id):
    seqfile = seq_dir / f"{unit_id}.seq"
    if not seqfile.exists():
        return None
    seq = [ln.strip() for ln in seqfile.read_text().splitlines() if ln.strip()]
    i = pos.get(unit_id, 0)
    i = min(i, len(seq) - 1)
    pos[unit_id] = pos.get(unit_id, 0) + 1
    return seq[i]

while True:
    for p in sorted(req_dir.glob("*.json")):
        if p.name in seen:
            continue
        seen.add(p.name)
        try:
            req = json.loads(p.read_text())
        except Exception:
            continue
        unit_id = req.get("unit_id")
        run_id = req.get("run_id")
        verdict_word = next_verdict(unit_id)
        if verdict_word is None:
            continue  # simulate: daemon/grader never responds for this unit
        if verdict_word == "pass":
            result = {"run_id": run_id, "model": req.get("model"), "unit_id": unit_id,
                      "kind": "preflight", "success": True, "score": 100,
                      "verdict": "MERGE", "gate": "pass", "reason": "stub-pass"}
        else:
            result = {"run_id": run_id, "model": req.get("model"), "unit_id": unit_id,
                      "kind": "preflight", "success": True, "score": 0,
                      "verdict": "BLOCK", "gate": "fail", "reason": "stub-fail"}
        tmp = res_dir / f"{run_id}.json.tmp"
        tmp.write_text(json.dumps(result))
        tmp.rename(res_dir / f"{run_id}.json")
        try:
            p.unlink()
        except OSError:
            pass
    time.sleep(0.1)
PYEOF

python3 "$STUB_DAEMON" "$REQ_DIR" "$RES_DIR" "$SEQ_DIR" &
DAEMON_PID=$!
sleep 0.3   # let the watcher loop come up before we submit anything

# ── (a)+(b)+(c): run the full battery against the stub daemon+model ─────────
SESSION_ROOT="$WORK/sessions"
CARD_OUT="$WORK/card.txt"

echo "== (a)/(b)/(c) full battery: aggregation + disguise + unreachable-per-run =="
rc=0
STDOUT_ERR="$WORK/run1.out"
PFR_TASKS_DIR="$TASKS_DIR" \
PFR_SPOOL_REQ="$REQ_DIR" PFR_SPOOL_RES="$RES_DIR" \
PFR_MODEL_CMD="$MODEL_CMD" \
PFR_SESSION_ROOT="$SESSION_ROOT" \
PFR_RUNS_N=3 \
PFR_POLL_TIMEOUT_S=3 PFR_POLL_INTERVAL_S=1 \
  "$RUNNER" candidate-model-x --out "$CARD_OUT" > "$STDOUT_ERR" 2>"$WORK/run1.err" || rc=$?

check "a1 exit code is 1 (detain — B and C missed threshold, ran fine)" "$rc" "1"

CARD="$(cat "$CARD_OUT" 2>/dev/null || true)"
contains  "a2 card lists TA"                      "$CARD" "TA"
contains  "a3 TA pass count is 2/3"                "$CARD" "2/3"
contains  "a4 card lists TB"                      "$CARD" "TB"
contains  "a5 TB pass count is 1/3"                "$CARD" "1/3"
contains  "a6 card lists TC"                      "$CARD" "TC"
contains  "a7 TC pass count is 0/3 (never a false pass)" "$CARD" "0/3"
contains  "a8 overall recommended verdict is detain" "$CARD" "recommended verdict: detain"
not_contains "a9 cross-cutting '*' row T99 not treated as a task" "$CARD" "T99"

ERRLOG="$(cat "$WORK/run1.err" 2>/dev/null || true)"
contains "a10 stderr loudly flags the never-answered fixture-c run(s)" "$ERRLOG" "NO RESPONSE"
contains "a11 stderr states it is never assuming a pass" "$ERRLOG" "never assum"

MODEL_INVOCATIONS="$(wc -l < "$MODEL_LOG" | tr -d ' ')"
check "a12 model command invoked exactly 9 times (3 tasks x 3 runs)" "$MODEL_INVOCATIONS" "9"

# ── (b) disguise invariant across every session worktree ever created ───────
LEAKED_MANIFEST="$(find "$SESSION_ROOT" -name 'manifest.tsv' 2>/dev/null | wc -l | tr -d ' ')"
LEAKED_TRAPS="$(find "$SESSION_ROOT" -name 'traps.tsv' 2>/dev/null | wc -l | tr -d ' ')"
PROMPT_COUNT="$(find "$SESSION_ROOT" -name 'PROMPT.md' 2>/dev/null | wc -l | tr -d ' ')"
check "b1 manifest.tsv NEVER copied into any session worktree" "$LEAKED_MANIFEST" "0"
check "b2 traps.tsv NEVER copied into any session worktree" "$LEAKED_TRAPS" "0"
check "b3 PROMPT.md present in all 9 session worktrees" "$PROMPT_COUNT" "9"

# ── (d) fully-unreachable daemon: whole battery refuses to start ────────────
echo "== (d) spool req dir does not exist at all -> fail-loud abort =="
: > "$MODEL_LOG"   # reset invocation counter
rc=0
PFR_TASKS_DIR="$TASKS_DIR" \
PFR_SPOOL_REQ="$WORK/no-such-spool/req" PFR_SPOOL_RES="$WORK/no-such-spool/res" \
PFR_MODEL_CMD="$MODEL_CMD" \
PFR_SESSION_ROOT="$WORK/sessions-d" \
PFR_RUNS_N=3 \
  "$RUNNER" candidate-model-y > "$WORK/run2.out" 2>"$WORK/run2.err" || rc=$?
check "d1 exit code is 2 (fail-loud abort, never a silent pass)" "$rc" "2"
ERRLOG2="$(cat "$WORK/run2.err" 2>/dev/null || true)"
contains "d2 stderr explains the daemon is unreachable" "$ERRLOG2" "unreachable"
D_INVOCATIONS="$(wc -l < "$MODEL_LOG" | tr -d ' ')"
check "d3 model command never invoked (aborted before driving any model)" "$D_INVOCATIONS" "0"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL PREFLIGHT-RUNNER TESTS PASS"
