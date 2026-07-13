# Mechanized Anti-Clobber Fix (SYNC-SCHEDULE) — Report

**Date:** 2026-07-13
**Branch (charon-private):** `feat/anti-clobber-session-start` — NOT pushed (manager lands)
**Branch (v5 docs repo):** `feat/anti-clobber-session-start` — NOT pushed (manager lands)

## Root cause (recap)

A session's bootstrap read a STALE handoff because:
1. `check_push_status.sh` hard-coded `origin/main`. The charon repos default to `master`,
   so `git rev-list --count origin/main..HEAD` silently resolved nothing, `2>/dev/null ||
   echo 0` masked it, and the script printed a **false** "✓ up to date with origin/main"
   while local `master` was really 2 commits behind (proven below).
2. `fleet/handoff.sh` generated a title line `\${SESSION:-unknown}` that was **never
   expanded** (escaped `\$`), so every generated handoff literally printed the placeholder
   text instead of the real session name — a copied/stale file was indistinguishable from
   a fresh one (as happened in commit `3647e0e`, which seeded `mace-windu`'s handoff with
   `obi-wan`'s old content).

## What changed, per file

### 1. `fleet/hooks/session-start.sh` (NEW)
SessionStart hook. Runs `fleet/sync-checkouts.sh` FIRST (FF-only, dirty-safe) against
`/home/stack/code/charon` (product) and `/home/stack/charon-private` (rig) — this is the
primary clobber-prevention. Then reports freshness against the **real** resolved upstream
(`git rev-parse --abbrev-ref --symbolic-full-name @{u}`, falling back to
`git symbolic-ref refs/remotes/origin/HEAD`) — never a hardcoded branch name. If a repo is
still behind after the sync attempt (dirty or diverged, so the FF was skipped), it prints a
loud `STALE` banner and a closing "do NOT trust a handoff until reconciled" line. Always
exits 0 (SessionStart hooks must not block session start); the banner is the signal.
Supports `SESSION_START_PRODUCT` / `SESSION_START_PRIV` / `SESSION_START_SYNC_SH` env
overrides for testing.

### 2. `/home/stack/v5/docs/tools/check_push_status.sh`
Replaced every hardcoded `origin/main` with a per-repo `resolve_upstream()` (same
`@{u}` → `origin/HEAD` fallback chain). If upstream can't be resolved at all, it now
reports that explicitly (`⚠ could not resolve upstream`) instead of silently defaulting.
Kept the three-ring output shape (WIP / unpushed / behind) and the push/pull command hints,
now parameterized on the resolved branch name instead of a literal `main`.

### 3. `/home/stack/.claude/settings.json`
Added a 4th `SessionStart` hook command entry (kept the existing 3):
```json
{
  "type": "command",
  "command": "bash /home/stack/charon-private/fleet/hooks/session-start.sh 2>&1 || true",
  "statusMessage": "Anti-clobber: syncing checkouts + freshness check..."
}
```
Verified `python3 -c "import json;json.load(open('/home/stack/.claude/settings.json'))"`
still parses; `diff` against a pre-edit backup showed only the intended addition (backup
removed after verification).

### 4. `fleet/handoff.sh` (hardened)
- Fixed the display bug: the title now shows the **real** `$SESSION` (was literally
  printing `${SESSION:-unknown}` as text).
- `SESSION` is now **required** (`SESSION="${SESSION:?SESSION env var required...}"`) —
  refuses to generate an anonymous/mislabeled handoff.
- Added a **Provenance** section stamped into every generated handoff:
  `**Session:** <name>`, `**Generated:** <utc>`, and a `Product HEAD` / `Rig HEAD` line per
  repo showing the short SHA and freshness vs. the **resolved** upstream (marks `⚠ STALE:
  N commit(s) behind <upstream>` when behind). A copied-from-another-session file now
  carries a visibly wrong/mismatched session name and stale SHAs instead of looking current.

### 5. `fleet/handoff-check.sh` (hardened)
Added two new check sections:
- `[provenance]`: parses `**Session:** <name>` from the handoff and compares it to the
  session slug in the filename (`SESSION-HANDOFF-<name>.md`). Mismatch → **FAIL** ("looks
  like a COPIED/stale placeholder handoff from another session"). Missing stamp → FAIL.
- `[freshness]`: FAILs if the handoff body contains the `⚠ STALE` marker that
  `handoff.sh` now stamps when a repo was behind its upstream at generation time.

### Supporting changes
- `fleet/sync-checkouts.sh`: added `SYNC_CHECKOUTS_PRODUCT` / `SYNC_CHECKOUTS_PRIV` env
  overrides (defaults unchanged) so tests can point it at throwaway repos.
- `fleet/tests/session-start-hook.test.sh` (NEW): FAIL-ON-REVERT test with a throwaway
  bare "origin" + two clones. Covers fresh (no STALE banner), stale-but-clean (sync FFs it,
  then reports current), stale-and-dirty (sync refuses to FF, hook prints the loud STALE
  banner), and a regression guard that greps the hook's *code* (comments excluded) for a
  hardcoded `origin/main`. **10/10 pass.**
- `fleet/tests/submit-checkin.test.sh`: fixed a **pre-existing, unrelated red** discovered
  while running the full gate — the test's isolated temp fleet copied `submit.sh` and
  `checkin.sh` but not `repo-registry.sh`, which `submit.sh` now sources (MULTI-REPO
  fold-in). Every submit died with "No such file or directory" before reaching the
  auto-check-in block it exists to test. Fix: copy `repo-registry.sh` into the fixture too.
  **7/7 pass** (was 0/7).

## Test evidence

**False-pass reproduction (OLD logic on a master-default repo):**
```
$ git -C /home/stack/code/charon rev-list --count origin/main..HEAD 2>/dev/null || echo 0
0
$ git -C /home/stack/code/charon rev-list --count HEAD..origin/main 2>/dev/null || echo 0
0
[Nnyan/charon] ✓  up to date with origin/main   <-- FALSE PASS (origin/main doesn't exist on this repo; real upstream is origin/master)
```

**Same false-pass reproduced on a throwaway clone reset 2 commits behind real origin/master:**
```
count=0 behind=0
[Nnyan/charon] ✓  up to date with origin/main   <== FALSE PASS (2 behind, undetected)
```

**NEW logic on the same behind clone (resolve_upstream → origin/master):**
```
[Nnyan/charon (product)] ⬇  5 commit(s) behind origin/master (unpulled — pull before working):
    git -C <clone> pull --ff-only origin master
```
(behind-count differs from the 2-commit hand example because the clone fixture and the
live repo advanced between the two demo runs — the material point, that the false "up to
date" silently disappears and a real behind-count is reported, holds in both cases.)

**NEW check_push_status.sh on the real (current) repos:**
```
[Nnyan/charon (product)] ✓  up to date with origin/master
[charon-private (fleet/rig)] ✓  up to date with origin/master
```

**session-start.sh hook, real repos (both current):**
```
== session-start: syncing local checkouts (FF-only, dirty-safe) ==
sync[product]: master current
sync[rig]: master current
[product] OK — current with origin/master (ac02dbd)
[rig] OK — current with origin/master (937bb3f)
session-start: all repos current — safe to trust the latest committed handoff.
```

**session-start-hook.test.sh (throwaway fixtures, all 4 scenarios):** 10/10 PASS —
including the STALE-DIRTY case:
```
== (c) STALE-DIRTY: origin advances again, clone has an uncommitted tracked change -> FAIL LOUD ==
PASS: c1 sync-checkouts refuses to FF a dirty repo
PASS: c2 hook prints a loud STALE banner when FF failed
PASS: c3 hook prints the do-not-trust closing line
```

**settings.json parse check:**
```
$ python3 -c "import json;json.load(open('/home/stack/.claude/settings.json'))"
JSON parses OK  (diff vs pre-edit backup: only the new hook entry added)
```

**Full fleet gate:**
```
$ bash fleet/gate.sh
... 14 tests ...
summary: 14 passed, 0 failed
```

**Board validation:**
```
$ bash fleet/validate_board.sh fleet
... (WARNs only, all pre-existing to-be-created-file notices, unrelated to this ticket) ...
GREEN board structurally valid
```

## Note on unrelated concurrent activity

`fleet/state/ROADMAP.tsv` and `fleet/board/REACHABILITY-GATE.md` show uncommitted changes
in this checkout that were **not** made by this session (working tree was clean at task
start; these files reference a different ticket, REACHABILITY-GATE, added by what appears
to be another concurrent session sharing this checkout). They are **not** included in this
branch/commit — left untouched to avoid clobbering that other session's live work.
