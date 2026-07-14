# NO-DARK-WORK review note

Land `fleet/dark-work-check.sh` — a single hermetic, fail-on-revert tested
script that mechanizes BOTH chronic "dark work" strands called out in the
ticket accept-criteria:

- **REGISTER leg** — scan running claude/opencode PIDs, cross-reference the
  session-bridge DB (`~/.charon/session-bridge.db`) for active rows
  (last_seen within `SESSION_BRIDGE_TTL`, default 600s), and flag any
  running PID whose pid has no matching active row. Pairs with auto-
  register on session start (Claude via the existing SessionStart hook;
  opencode/CG via the proxy wrapper — both slated for follow-up tickets
  in this strand).
- **PICKUP leg** — scan the natural job registry (state/agent-logs/*.txt +
  state/agent-briefs/*.md) for any launched job whose ticket id is NOT
  in `state/submitted/<ticket>`, `state/done/<ticket>`, or
  `state/needs-push/<ticket>`, and not explicitly waived via
  `state/jobs/waived/<droid>-<ticket>`. LIVE jobs (mtime within
  `DARK_WORK_LIVE_AGE_S`, default 600s) are NOT flagged — only STRANDED
  results.

Fail-on-revert: 19/19 assertions pass on `--selftest` (covers A=register
RED/GREEN, B=pickup RED/GREEN with 5 distinct conditions, C=--waive
operator exception, D=--json output structure, E=default both-legs
exits non-zero when either is RED). The check is offline-testable: a
throwaway `tmp/bridge.db` + a stub `ps-stub.sh` driving 3 known PIDs (1
registered, 2 dark) is the entire surface the register leg depends on;
the pickup leg depends on tmp state dirs only. `shellcheck -S warning`
returns 0 (no findings). `bash -n` syntax-clean.

Subcommands: default (both legs, non-zero on either RED), `--register`,
`--pickup`, `--json` (machine-readable `{register:[...], pickup:[...]}`
on RED; empty on GREEN), `--waive <job> <reason>` (records an explicit
operator exception — the only way to NOT pick up a result is to record
WHY; a silent no-op is impossible). Test hooks documented at the top of
the script so future tests can stub `ps` / bridge DB / fleet / now.

**Out of scope (per the ticket's "owns: a single new script" rule and
the `disjoint from all product work` line)**: I did NOT wire
`dark-work-check.sh` into `preflight.sh` as a tracked red, NOR into
`end-session.sh` as a phase-2 gate, NOR into `session-start.sh` as a
register check — those are owned by F19 (bridge-unregister-trap, the
exit complement) and F38 (handoff-mechanize, where the omitted-pointer
strand happens). The check script is the SINGLE chokepoint they will
call; the wiring is their file.

Also NOT in scope: auto-register hooks for opencode/CG (F19), the
SessionStart auto-register for Claude (mentioned in the ticket but the
existing `session-start.sh` does not register either — adding it is a
separate ticket, F19's complement).
