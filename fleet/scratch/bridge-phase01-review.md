# Adversarial review — durable session-bridge Phase 0-1

**Scope:** read-only audit of Repo A (`~/.config/opencode/session-bridge/` daemon.py, proxy.py,
idempotency.py, test_daemon.py) + Repo B (public `/home/stack/code/charon` guard/CI change). Live
daemon (`~/.charon/bridge.sock`) NOT touched. All findings verified by re-running the tests/gates
myself against scratch state.

## VERDICT: SHIP — the Repo B public-repo commit is safe. Repo A is a build-rig (uncommitted) change with Phase-2 follow-ups only.

The #1 worry is **REFUTED**: a real coordinator IP does NOT slip through the guard.

---

## The #1 concern — does the guard catch a coordinator IP `10.0.1.51`? YES.
- `check_file()` breaks on first match. For `10.0.1.51` the generic `10\.\d+\.\d+\.\d+` pattern
  (index 0) fires FIRST → violation `"internal IP (10.0.0.0/8)"` → commit blocked. It is **caught**,
  not missed. The named `10\.0\.1\.\d+` "coordinator LAN subnet" pattern at index 1 is redundant and
  **never reached inside check_file** (generic always wins) — only the *description string* differs,
  never the catch. `192.168/16` and `172.16/12` are caught by their own patterns. Verified: raw scan
  of the whole tree + the 3 new regression tests + full pytest.
- Report's own note (lines 108-117) about the description-string discrepancy is **accurate and
  honest** — it flagged it rather than silently "fixing" the spec. Not a blocker.
- Residual (minor): guard covers dotted-quad RFC1918 + `4-lom`/`charon-vm` hostnames + `/home/stack`
  + `charon-private` + 40-hex. An arbitrary coordinator *hostname* (not those two) or IPv6 is NOT
  guarded — but proxy.py by construction never embeds the real host (only `$COORDINATOR_HOST`, real
  value in gitignored `bridge-hosts.env`), so acceptable defense-in-depth.

## Exceptions file — masks NO real secret. VERIFIED.
- Raw scan with exceptions DISABLED = 104 hits. Every masked entry is a **test fixture**
  (`test_public_clean.py`, `test_check_security.py` synthetic `192.168.1.100` etc.), the **guard's
  own pattern source** (`check_public_clean.py:12-22`), or **pre-existing docs narrative** (4-lom
  runner label, pinned Action SHAs, `/home/stack/charon-private/...` and `charon-vm` in review-log
  ADRs). No real coordinator IP/secret is whitelisted. Per-file line lists — not over-broad globs.

## Guard wiring — runs and is green. VERIFIED.
- `gate_runner.py` CHECKS gets 6th tuple `("public-clean")`; `.pre-commit-config.yaml` local hook
  (`always_run`, `pass_filenames:false`). `PYTHONPATH=src charon.cli gate` → all 6 OK incl.
  `[public-clean]`. `pytest -q` → **1244 passed**, exit 0. No product regression.

## Repo A core — all four gates hold. VERIFIED (15/15 test_daemon pass, exit 0).
- **NB1 TOTAL:** `_row_to_dict` builds from `_PEER_VISIBLE_COLUMNS` allowlist; `lease_token` absent;
  fails CLOSED on unknown column (test plants `future_secret` → excluded). Traced every peer path
  (board/register/claim/update/nudge/ack/unregister/release) — `lease_token` only ever a top-level
  field for the CALLER's OWN token; never another session's, never a row round-trip. No bypass found.
- **NB2:** `seq_counter` table, `_next_seq()` SELECT+UPDATE in the same txn/commit as the nudge write
  (daemon is single-threaded → no race); `_sort_key` None-safe `(0,ts)`<`(1,seq)`; restart-survival
  + mixed None/int proven.
- **Lease model:** `os.kill`/PID only in COMMENTS — zero authority use; claim-steal + purge keyed
  purely on `lease_expires_at` vs `_now()`; clock-based → cross-host correct. Live lease lapses only
  if a session stops polling >600s (identical to today's TTL); dead claim stealable/purged at 600s.
- **G1:** non-destructive ack + `delivered_at` + bounded 120s redeliver→auto-ack + 24h TTL GC
  (stderr-logged) + queue caps reject explicitly (`target queue full`/`(bytes)`) + oversized-frame
  `-32000`. No silent truncation/drop.
- opencode.json inert (BRIDGE_SOCKET=`.../.charon/bridge.sock` explicit-wins; HOST=""/REPO=charon
  dead). No `src/` import of the bridge — product independent.

---

## Ranked follow-ups — NONE block the Repo B commit
1. **(Recommended, non-blocking) Line-number exceptions are content-blind + position-fragile.** Now
   that the file went `{}`→~100 lines, a future edit to an exempted line, or an inserted line
   shifting numbers, can silently mask a real leak (false green) or re-flag benign content. Prefer
   position-independent inline `# public-clean: allow` waivers (already supported) where practical,
   or add a test asserting each exempted line still matches its expected benign shape.
2. **(Policy, non-blocking, pre-existing)** Exceptions bless committed dev-meta
   (`/home/stack/charon-private/...`, `charon-vm`) in review-log docs/tests. Per the operator's own
   public-repo-no-personal-info rule these are arguably scrub-worthy; exempting entrenches them.
   Not introduced by this change — operator should consciously pick scrub-vs-exempt.
3. **(Phase-2 semantic, Repo A)** 120s redeliver window AUTO-ACKS (drops) an unacted message if the
   consumer is offline >120s after first delivery = bounded message loss. Dormant now (no push
   consumer); Phase-2 idempotency+renewer must account for it.
4. **(Back-compat, Repo A)** board/update nudge reads changed destructive→non-destructive: a legacy
   consumer reading the `nudge_messages` array (not the `nudges` counter) re-sees a nudge for ≤120s.
   Activates only on daemon restart; call out in the cutover notes.
5. **(Cosmetic)** Named `10.0.1.\d+` pattern never fires in check_file (generic wins); if a distinct
   "coordinator" description in output is wanted, reorder it before the generic. Report documents this.
6. **(Doc drift, self-flagged)** `tools/gates.json` charon-gate "covers" text omits public-clean.
