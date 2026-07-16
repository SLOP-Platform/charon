# CONFIG-SSOT-PROPAGATE — per-ticket review fragment
#
# Ticket:    CONFIG-SSOT-PROPAGATE (charon-private; tier=strong; difficulty=4; work_class=rig-meta)
# Branch:    feat/config-ssot-propagate
# Files:     fleet/config-manifest.tsv, fleet/config-sync.sh,
#            fleet/checks/config-ssot-gate.sh, fleet/tests/config-ssot.test.sh
#            + fleet/RECONCILE-CONFIG-DRIFT.md (the operator-snapshot report; accept-criterion
#              deliverable — file is in fleet/ to stay on-side with the per-ticket owns rule
#              without touching docs/ or other owned territory)
#            + this fragment (docs/review-log/CONFIG-SSOT-PROPAGATE.md; the lone exception
#              to the per-ticket owns rule, by design)
#
# ## What landed
#
# The full class fix for config-siloing (operator directive, 2026-07-14):
#   - fleet/config-manifest.tsv: git-tracked SSOT (11 providers keyed on the 4-LOM gateway,
#     per fleet/state/CG-PROVIDERS.md). Columns: provider|key_env|base_url|tiers|note. Strict
#     5-column TSV (manifest is well-formed-only; a malformed row is a HARD ERROR, not a
#     silent skip — gate test #8 proves it).
#   - fleet/checks/config-ssot-gate.sh: REDs when any source (local ~/.charon, 4-LOM
#     /data/providers.json) diverges from the manifest. Names the drift (MISSING-LOCALLY /
#     MISSING-ON-GATEWAY / BASE-URL MISMATCH / KEY-ENV MISMATCH / UNEXPECTED-LOCAL /
#     UNEXPECTED-ON-GATEWAY) and the fix command per row. UNREACHABLE sources are HARD-RED,
#     not silently satisfied (the load-bearing bug this gate exists to close — gate test #5
#     + fail-on-revert #11 prove it). --advisory mode for boot-time visibility; default
#     mode is the gate.
#   - fleet/config-sync.sh: propagates manifest -> BOTH local ~/.charon/providers.json AND
#     the 4-LOM gateway. The GATEWAY path uses the OPERATOR-DECIDED write-path (commit
#     3b27786 on origin/master, 2026-07-15): `ssh -i ~/.ssh/4lom stack@10.0.1.60 docker
#     exec charon-gateway-1 sh -lc 'CHARON_HOME=/data python3 -m charon.cli providers set
#     <name> --base-url <url> --key-env <env>'` — i.e. docker exec into the live container
#     going through the charon CLI's idempotent setter (NOT a raw `cat > /data/providers.json`,
#     which the prior stub considered but the operator explicitly chose to avoid). The
#     gateway path: (1) snapshots /data/providers.json to *.bak-<UTC-ts> before any write
#     (matches add-provider.sh's backup convention; one-command rollback), (2) runs
#     `providers set` per manifest row (idempotent; each is a separate ssh+docker hop so a
#     mid-write failure leaves the gateway in a partial-but-recoverable state — re-run to
#     converge), (3) verify-after via `charon providers list` to confirm every manifest row
#     is present in the live gateway (HARD ERROR on any missing row; snapshot-rollback hint
#     printed). --dry-run prints the exact docker-exec command sequence without applying.
#     --gateway without --force is a REFUSAL (rc=2) — production write never accidental
#     (test #10 proves it). --volume path remains as an alternate (not chosen by the
#     operator; kept for future re-decisions).
#   - fleet/tests/config-ssot.test.sh: 33 tests, all hermetic (env-var fixtures; no live
#     4-LOM, no ~/.charon). Covers: in-sync -> GREEN, drift -> RED, MISSING-LOCALLY,
#     MISSING-ON-GATEWAY, BASE-URL MISMATCH, UNREACHABLE-hard-RED, --advisory mode,
#     UNEXPECTED-LOCAL orphan detection, malformed manifest -> HARD ERROR, SYNC writes +
#     idempotency, --gateway refusal without --force, --gateway --force --dry-run prints
#     the exact charon providers set commands, fail-on-revert (proves the unreachable-
#     hard-RED is load-bearing), key-value leak prevention.
#   - fleet/RECONCILE-CONFIG-DRIFT.md: the one-time RECONCILE report of the local-vs-gateway
#     drift at the moment this ticket landed. Local has 1 of 11 manifest providers (the 10
#     missing are the drift the operator's "thin pool" reading pointed at). Regenerate
#     anytime: `fleet/config-ssot-gate.sh --report`.
#
# ## Decisions / non-obvious choices
#
# 1. **Tiers column = space-separated, not tab-separated.** The "paid free" rows initially had
#    a tab between "paid" and "free" which made the parser see 6 fields. Switched to
#    space-separated. Format doc clarified in the manifest header.
#
# 2. **The bash parameter-expansion bug.** `GATEWAY_RCMD="${GATEWAY_PROVIDERS_RCMD:-docker exec
#    -i charon-gateway-1 cat /data/\{}}"` — bash's parser eats the `{}` in the parameter
#    default as if it were a nested parameter expansion; the resulting default value had an
#    extra `}`. Workaround: separate `[ -n "${X:-}" ] && Y=$X || Y='default'` pattern with the
#    default in single-quotes. Documented inline. This was a 20-min detour; the lesson: bash's
#    `${VAR:-default}` is brittle when the default contains `{}` — use a separate if-stmt
#    for brace-bearing defaults.
#
# 3. **UNEXPECTED-LOCAL is drift, not in-sync.** A local row not on the manifest (orphaned
#    local entry) is a separate drift class — it could be a stale local entry from a removed
#    provider, or a hand-edited local addition that never made it to the manifest. Either
#    way, the operator wants to know. UNEXPECTED-LOCAL is RED.
#
# 4. **SECRETS: names only, never values.** The gate compares key_env NAMES from
#    ~/.charon/secrets.json (best-effort). It never reads, transports, or prints key
#    VALUES. Test #12 explicitly seeds a fixture with an `api_key` value and asserts it
#    never appears in the output. The SYNC tool writes key_env names + base_url strings
#    only; secrets.json is NOT touched, and `charon providers set` is called WITHOUT the
#    key value (the key is a host-side env var on the 4-LOM; this tool only names which
#    env var the provider should consult).
#
# 5. **Write-path = docker exec into charon-gateway-1, NOT a raw `cat > /data/providers.json`.**
#    The operator explicitly chose (commit 3b27786) the `charon providers set` route: it
#    goes through the CLI's atomic-write library (config/providers.py) rather than
#    bypassing it with a raw pipe. The raw-cat approach was the prior stub's
#    `--write-path=exec`; the chosen path is the SAME exec, but using charon CLI rather
#    than overwriting /data/providers.json directly. The trade-off: the raw cat was a
#    one-shot overwrite (zero-downtime but partial-write-invisible); the chosen path is
#    per-provider idempotent (each row is a separate atomic set; mid-write failures are
#    recoverable by re-running). The `--write-path=volume` alternate is kept but
#    unchosen — available for a future re-decision.
#
# 6. **Manifest is git-tracked in the PRIVATE rig, not public.** The active-provider set
#    is sensitive (a public view leaks which providers the operator is keyed into, an
#    attack-surface enumeration). Header of the manifest calls this out.
#
# 7. **The 4-LOM sync writes ONLY manifest rows; it does NOT remove a gateway provider that
#    is absent from the manifest.** This is by design: the manifest is the LIST OF WHAT
#    WE WANT, but the gateway may have providers the operator is still using that we have
#    not yet added to the manifest (e.g. a manually-keyed one-off). The gate surfaces
#    `UNEXPECTED-ON-GATEWAY` rows so the operator can decide. If a manifest REQUIRES a
#    gateway to drop a provider, that is a `charon providers remove <name>` invocation —
#    intentionally out of scope for the SYNC tool (a destructive op belongs in its own
#    explicit ticket, not in a sync).
#
# ## Wiring (out of ticket scope by owns rule; called out for the operator)
#
# The ticket's accept says "Wired into validate_board advisory first." This is the one
# piece I COULD NOT do without breaking the per-ticket owns rule (validate_board.sh and
# preflight.sh are owned by other tickets). The clean wiring paths are:
#   - preflight.sh:detect_config_drift (already calls config-drift.sh --advisory; could
#     be swapped to config-ssot-gate.sh --advisory in a 1-line change — config-drift.sh
#     is currently degraded per RIG-STATE-HYGIENE and the SSOT gate is the replacement
#     of record)
#   - validate_board.sh near the parallelizability-gate subprocess block (the existing
#     pattern for "ADVISORY board-wide surface of <X>"; 8-line addition)
#   - reds.tsv as a NEW tracked red `config-ssot-drift` (mechanized like the existing
#     `board-validator-red` auto-registered red; the gate becomes a build-gate not just
#     an advisory)
#
# I did NOT edit those files because they are not in this ticket's owns list. The gate
# is a self-contained, drop-in script — the operator can wire it with the snippet in
# this fragment when ready.
#
# ## Verification
#
#   bash fleet/tests/config-ssot.test.sh
#     -> 33 passed, 0 failed (covers GREEN, all drift classes, --advisory, malformed
#        manifest, idempotent sync, gateway-refusal, gateway-dry-run, fail-on-revert,
#        key-leak prevention)
#
#   bash fleet/checks/config-ssot-gate.sh
#     -> exit 1 (RED: 10 drift locally + 1 unreachable gateway in this worktree)
#
#   bash fleet/checks/config-ssot-gate.sh --report
#     -> exit 0, prints the same drift (advisory mode for visibility)
#
#   bash fleet/config-sync.sh
#     -> local-only sync: writes ~/.charon/providers.json from the manifest (idempotent
#        on second run; backs up existing file with .bak-<UTC-ts>)
#
#   bash fleet/config-sync.sh --gateway
#     -> rc=2 REFUSED with both write-path options documented
#
#   bash fleet/config-sync.sh --gateway --force --dry-run
#     -> exit 0, prints the exact ssh + docker exec charon providers set commands
#        (no network/ssh calls; the operator can eyeball the commands before re-running
#        without --dry-run)
