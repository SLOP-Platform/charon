#!/usr/bin/env bash
# memory-scripts.test.sh — FAIL-ON-REVERT self-test for fleet/memory/*.sh.
#
# Hermetic: a STUB `basic-memory` on PATH under mktemp -d records every invocation.
# Never touches the real vault, never hits the network. ~1s.
#
# WHY THIS EXISTS
#   fleet/memory/migrate-frontmatter.sh and curation.sh mutate the operator's LIVE
#   basic-memory vault through `basic-memory tool edit-note` / delete/move. They shipped
#   with ZERO test coverage — the ticket's own review-log records "no memory suite in
#   CI_SUITES" — and migrate-frontmatter.sh defaulted to APPLY, so running it bare
#   rewrote every note in the vault. curation.sh (its sibling) and fleet/branch-reaper.sh
#   both default to dry-run and demand an explicit --apply.
#
# GREEN-IS-NOT-PROOF: exit 0 does not prove the migration is correct. Each case names the
# exact revert that must turn it RED.
#
# Covers:
#   (a) migrate-frontmatter DEFAULTS TO DRY-RUN — a bare run performs NO write call.
#       Reverting `DRY_RUN=1` to `DRY_RUN=0` makes this RED.
#   (b) migrate-frontmatter --apply DOES write. Guards against a "fix" that disables the
#       tool entirely; a script that can never act is as useless as one that always acts.
#   (c) curation.sh DEFAULTS TO DRY-RUN — no destructive call without --apply.
#       Removing its APPLY guard makes this RED.
#   (d) both scripts are syntactically valid (`bash -n`) — a broken script that is never
#       invoked in CI would otherwise rot undetected.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIG="$HERE/memory/migrate-frontmatter.sh"
CUR="$HERE/memory/curation.sh"
fails=0
ok(){ echo "  ok   — $1"; }
bad(){ echo "  FAIL — $1"; fails=$((fails+1)); }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

# Stub basic-memory: logs argv, and emits one fake note so the migration loop has work.
cat > "$D/basic-memory" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "$BM_CALLS"
case "$*" in
  status*)            echo '{"ok":true}' ;;
  *search-notes*)     echo '{"results":[{"permalink":"note-one"}]}' ;;
  *read-note*)        echo '{"content":"---\npermalink: note-one\n---\nbody\n"}' ;;
  *) : ;;
esac
exit 0
STUB
chmod +x "$D/basic-memory"
export PATH="$D:$PATH"

writes(){ grep -cE "edit-note|write-note|delete-note|move-note" "$1" 2>/dev/null || true; }

echo "== (a) migrate-frontmatter: bare run is DRY-RUN (no writes) =="
export BM_CALLS="$D/calls-a.log"; : > "$BM_CALLS"
timeout 60 bash "$MIG" >"$D/a.out" 2>&1
w=$(writes "$BM_CALLS")
if [ "$w" -eq 0 ]; then ok "no write call on a bare run"
else bad "bare run issued $w write call(s) — it defaults to APPLY"; fi
grep -qi "dry-run" "$D/a.out" && ok "reports DRY-RUN to the operator" \
  || bad "did not announce dry-run (silent no-op is its own defect)"

echo "== (b) migrate-frontmatter --apply DOES write (anti-over-block) =="
export BM_CALLS="$D/calls-b.log"; : > "$BM_CALLS"
timeout 60 bash "$MIG" --apply >"$D/b.out" 2>&1
w=$(writes "$BM_CALLS")
if [ "$w" -gt 0 ]; then ok "--apply issued $w write call(s)"
else bad "--apply wrote nothing — the tool cannot act at all"; fi

echo "== (c) curation.sh: bare run is DRY-RUN (no destructive call) =="
export BM_CALLS="$D/calls-c.log"; : > "$BM_CALLS"
timeout 60 bash "$CUR" >"$D/c.out" 2>&1
w=$(writes "$BM_CALLS")
if [ "$w" -eq 0 ]; then ok "no destructive call on a bare run"
else bad "bare run issued $w destructive call(s)"; fi

echo "== (d) both scripts parse =="
for f in "$MIG" "$CUR"; do
  bash -n "$f" 2>/dev/null && ok "bash -n $(basename "$f")" || bad "syntax error in $(basename "$f")"
done

echo
if [ "$fails" -eq 0 ]; then echo "memory-scripts: GREEN"; exit 0; fi
echo "memory-scripts: RED ($fails failing)"; exit 1
