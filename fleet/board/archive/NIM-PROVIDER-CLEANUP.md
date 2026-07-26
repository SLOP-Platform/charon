retired: |
  RETIRED 2026-07-26 — operator decision 26(c). Defects (a) false-FAILED add and (b) API key echo
  leak LANDED via ADD-PROVIDER-MECHANIZE-COMPLETE (d7e03ab, merged 9eaa4f5). Defect (c) free-tier
  limits is folded into FT-LIMITS-GROQ-RECONCILE, which already owns fleet/state/FREE-TIER-LIMITS.tsv
  — validate_board.sh proved the duplication by flagging the owns-collision the moment this ticket's
  owns were corrected to the real file. Nothing is lost: (c) was already deliberately deferred by
  docs/review-log/ADD-PROVIDER-MECHANIZE-COMPLETE.md:67, and the catalog ticket is its proper home.
repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 2
branch: fix/nim-provider-cleanup
depends_on: ADD-PROVIDER-MECHANIZE-COMPLETE
real-dep: ADD-PROVIDER-MECHANIZE-COMPLETE — TRUE single-writer sequencing, NOT merge order. It owns
  fleet/add-provider.sh AND fleet/add-provider-interactive.sh, the same two files this ticket edits,
  and it is ALREADY IN FLIGHT (worktree charon-private-wt/ADD-PROVIDER-MECHANIZE-COMPLETE at d7e03ab).
  Two concurrent writers of the onboarding scripts is precisely the collision class we ticket others
  for. Rebase onto its landed version; never co-write. Added 2026-07-26 after validate_board.sh caught
  the collision — my original claim that no live ticket owned these files was ASSERTED, not verified.
dep-kind: build
owns: fleet/state/FREE-TIER-LIMITS.tsv, fleet/tests/test_add_provider.sh
serial_justified: |
  ONE provider-onboarding surface: the two add-provider entrypoints plus the catalog they populate.
  The key-echo leak and the false-FAILED report are both defects in that same onboarding path, and the
  catalog entry is what onboarding is FOR — splitting them leaves a half-onboarded provider.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  The run IS a graded sample: record it into fleet/model-scorecard.tsv with the work_class above.
  One checkout, one agent — its OWN worktree.
source: |
  Operator action item V (long-standing, non-blocking). Observed during NVIDIA NIM onboarding.
corrected: |
  2026-07-26 — the original owns: named TWO FILES THAT DO NOT EXIST
  (`fleet/state/free_tier_catalog.json`, `fleet/tests/add-provider.test.sh`). Session cal-kestis
  (minimax-m3-together) caught it and STOPPED rather than inventing them. The real artifacts are
  `fleet/state/FREE-TIER-LIMITS.tsv` (a TSV, not JSON) and `fleet/tests/test_add_provider.sh`.
  Defects (a) and (b) landed via ADD-PROVIDER-MECHANIZE-COMPLETE; only (c) remains. Note
  docs/review-log/ADD-PROVIDER-MECHANIZE-COMPLETE.md:67 DEFERRED (c) deliberately — confirm with the
  operator that (c) is still wanted before dispatching again, and check FT-CATALOG-SEED for overlap.
note: |
  ## THREE DEFECTS IN THE PROVIDER-ONBOARDING PATH

  (a) **FALSE FAILURE REPORT.** `add-provider.sh` step 4 does not pass `--base-url`. Adding a
  NON-PRESET provider therefore reports FAILED even though the add actually SUCCEEDED. An operator
  who believes the report either re-runs it or abandons a provider that is in fact configured. A tool
  that lies about its own outcome is worse than one that fails.

  (b) **SECRET LEAK (do this one properly).** `add-provider-interactive.sh` ECHOES the API key as it
  is typed. It must read the key without echo (`read -rs` in bash, `getpass` in python) and must not
  print it afterwards in confirmations, logs, or error paths. Check the WHOLE script for the key
  reaching stdout/stderr — not just the prompt line. Keys in scrollback survive in terminal history,
  screen shares and recordings. This is the highest-value item here even though V is filed
  non-blocking [[security-is-a-ratchet-gate]].

  (c) **MISSING LIMITS.** NVIDIA NIM has no rate-limit / credit entries in the free-tier catalog, so
  free-tier planning cannot see it. Add its real limits — sourced, not guessed; record where each
  number came from. A wrong limit is worse than a missing one because planning will trust it
  [[use-free-tiers-to-their-limits]].
accept: |
  DONE-CONTRACT (observable, by EXECUTION):
  - (a) Adding a non-preset provider with an explicit base-url reports SUCCESS and the provider is
    actually present afterwards. Show the command and its output, before and after.
  - (b) PROVE the key never reaches the terminal: run the interactive add with a dummy key while
    capturing stdout+stderr, then grep the capture for that dummy key and show ZERO hits. A visual
    "looks fine" is not proof. Also confirm no key in any log file the script writes.
  - (c) NVIDIA NIM entries present in the free-tier catalog with a cited source per number.
  - Regression test in `fleet/tests/add-provider.test.sh` covering (a) and (b); the (b) test must FAIL
    if the no-echo read is reverted — red-proof it by execution and report BOTH exit codes.
  - NON-VACUOUS: a test that greps a capture that was never written passes trivially — assert the
    capture is non-empty first.
  - FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
  - Do NOT commit any real key. Use an obviously-fake dummy value.

## Dependencies & sequence

- **Depends on: NOTHING. Startable immediately**, fully concurrent with the Switchboard wave —
  rig-side, and no live ticket owns any of these four files (verified against the full `owns:` set of
  fleet/board/*.md, 2026-07-26).
- **Blocks:** nothing. Non-blocking cleanup; (b) is a real security fix and should not wait long.
- **Wave:** parallel lane, any time.
