# Review: 389@charon-private
**PR:** feat(reviewer-tab): headless reviewer tab with fail-loud preflight
**URL:** https://github.com/Nnyan/charon-private/pull/389
**Date:** 2026-08-02T04:42:35Z
**Reviewer:** reviewer-Tardis-3790787
**Author:** strong-2841812

## Verdict
BOUNCE

## Findings
- **Double-bash exec — the tab can never start.** reviewer-tab.sh execs `spawn-tab.sh <name> <color> bash <script> --wait <n> --retries <n>`; spawn-tab.sh then runs `wsl.exe ... bash "$RUN_SCRIPT" "$@"`, so the RUN_SCRIPT receives `$@ = (bash <script> strong --wait 3 --retries 6)`. Its final line is `printf 'exec %q "$@"'` → `exec bash "$@"` → `exec bash bash <script> ...`. Bash treats the second `bash` as a script *file* and dies (`bash: bash: cannot execute binary file`, exit 126 — reproduced locally). Every reviewer tab crashes on launch; the feature is 100% non-functional and the author clearly never ran it.
- **The Fault-2 fix is a silent no-op.** `CHARON_REVIEW_MODELS`, `CHARON_GATEWAY_TOKEN`, `CHARON_DROID_ID` are exported in the WSL shell that execs `wt.exe`, but env vars do NOT cross the wt.exe (Windows process) → new-tab `wsl.exe` boundary without WSLENV. spawn-tab.sh defines the `CHARON_TAB_ENV` mechanism precisely for this, but reviewer-tab.sh never populates it (and the RUN_SCRIPT "re-derive token" block is dead — it computes FLEET from the /tmp script and never sources env-registry.sh). So the tab's review-pool.sh silently falls back to the hardcoded `deepseek-v3,deepseek-r1` defaults → the exact wrong-model-id BOUNCE loop the PR claims to fix, now masked by a green preflight.
- **Preflight validates the wrong environment.** All fail-loud checks (binaries, gh auth, /v1/models) run in reviewer-tab.sh's *parent* (login) shell, not the non-login tab shell where the fault class actually lives; the models check is even guarded by `if [ -n "${CHARON_GATEWAY_TOKEN:-}" ]`, contradicting §4's "exit 4 on token-derivation failure" contract (a failed derivation silently skips the check). `/v1/models` is hardcoded to `http://10.0.1.60:8080` while the log line prints the never-set `$CHARON_GATEWAY_URL` (always `gateway=`), so it can probe a stale gateway and the operator can't tell.
- **Race: `rm -f "$RUN_SCRIPT"` runs immediately after async wt.exe returns.** The new tab boots a fresh wsl.exe (seconds on cold start); if it opens the script after deletion → `No such file or directory` → silent tab death, the exact "fail loud" failure the PR is built to prevent.
- **Raw-tier/chain mismatch.** `exec ... review-pool.sh "$TIER"` passes the uncanonicalized tier (`high`/`opus`/`med`/...) while the chain is derived from `canon_tier`, so the pool's tier-dependent behavior/logging disagrees with the models actually loaded.
- **The stated goal is a cover for the regression.** §7 openly punts the real failure mode (BOUNCE written durably on infrastructure failure) to PR #346; the preflight only catches missing binaries at *startup* — mid-run gateway/model failures still write fail-closed BOUNCE verdicts indefinitely. The one genuinely working fix here is the non-login-shell PATH append in spawn-tab.sh; the "gate fix" relocates detection to startup while leaving the BOUNCE-producing write path untouched.

## Fail-on-revert check
Reverting would drop the one functional fix — spawn-tab.sh's PATH append that restores ~/.local/bin (gh/opencode) inside wt-launched non-login tabs — re-introducing the silent `gh pr list` exit-127 "no claimable review items" BOUNCE loop.

## Status
Pending Manager dispensation
