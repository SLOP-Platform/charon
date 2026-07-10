# work_class ticket-schema build — report

Made `work_class` a required, validated field on every board ticket, backfilled all
non-parked tickets, and confirmed `capability/assign.py` already auto-resolves it (no code
change needed there — its ticket-meta reader was built ahead of the schema landing).

## 1. Schema change

Field: `work_class:` — one line, placed immediately after `tier:`, matching the existing
lowercase-with-colon single-line convention shared by `tier:`, `branch:`, `depends_on:`,
`owns:`, `prompt:` (confirmed from board/E1.md, board/N1.md, board/SR-13.md, etc. — no
`Status:`/`Owner:`-style capitalized fields exist on this board). The exact key
`work_class` was chosen (not `Work-Class`) because `capability/assign.py`'s
`read_ticket_meta()` already did `meta.get("work_class")` — the plumbing was built ahead of
the schema (see `capability/assign.py` docstring: "first consumer of the shared capability
brain"). Using any other casing/spelling would have required an assign.py code change;
using the exact pre-existing key made backfill alone sufficient to wire it up.

Taxonomy — single source of truth `capability/grades.py`'s `WORK_CLASSES` tuple (also
mirrored in `model-scorecard.sh`'s `VALID_CLASS`, per that module's own lockstep-discipline
comment), plus the literal `generalist` fallback bucket:
```
money-path, routing, ci-infra, refactor, bugfix, tests, greenfield-feature, docs,
frontend, generalist
```
Note this differs from the taxonomy sketched in the build brief (`greenfield` vs
`greenfield-feature`; missing `tests` and `docs`) — grades.py was read directly as the
ground truth per the brief's own instruction to not trust the sketch blindly.

Example (from `board/FB1.md`):
```
tier: sonnet
work_class: bugfix
branch: feat/fix-boundary-relimports
depends_on:
owns: tools/check_boundary.py, tests/test_boundary.py
prompt: /home/stack/charon-private/prompts/fb1.md
```

## 2. Validator change (`validate_board.sh`)

Added check **2b** (new Python block, right after the existing `depends_on` validity
check): for every ticket in the same `tickets` dict the rest of the script already builds
(via `glob.glob(board/*.md)`), read the `work_class` field and:
- RED `work-class-missing: <ticket> has no 'work_class:' field...` if the field is absent
  or empty.
- RED `work-class-invalid: <ticket> work_class '<value>' is not one of ...` if present but
  not in `WORK_CLASSES ∪ {generalist}` (imported live from `capability/grades.py`, not a
  hand-duplicated list, so the two can never drift).
- If `capability/grades.py` can't be imported at all, RED
  `work-class-check-failed: ...` (fail-closed, not silently skipped).

**Parked-ticket precedent followed:** `.md.parked` tickets are never validated for this (or
any other required field) because the script's `tickets` dict is built from
`glob.glob(os.path.join(board, "*.md"))` — a `.md.parked` file never matches that glob, so
it never enters the dict at all. This is the exact same mechanism the pre-existing D&S
standing-rule check documents in its own comment ("Parked ... are not scanned, so this
fires the moment a ticket is un-parked to live."). No new parked-handling logic was
invented; the new check simply lives in the same `tickets` dict everything else already
uses. **Important nuance found during grounding:** several tickets are labeled
"BACKLOG (parked)" or "PARKED" only in a comment line inside a `board/<ID>.md` file (e.g.
`CLIENT-CONNECT-GUI.md`, `DTC-1.md` .. `DTC-8-TEST-PATTERNS.md`, `OBS-CAPTURE.md`,
`OBS-UI.md`, `CONSOLE-PROVIDER-MGMT.md`, `SETUP-KEY-UX.md`, `SECRET-SCAN-ENVVAR-FP.md`,
`PUBLIC-CLEAN-LINT.md`) — the filename itself is still `*.md`, not `*.md.parked`, so
`validate_board.sh` DOES scan them and they DO require `work_class`. All of these were
backfilled (they're in the 101, not the 16 true `.md.parked` exemptions).

Done tickets are NOT exempted from the `work_class` check (only the pre-existing D&S check
exempts done tickets, per its own comment "Done tickets are exempt (historical)"; the other
required-field checks — `prompt` exists, `depends_on` valid — do not exempt done tickets
either, so `work_class` follows that majority precedent instead).

## 3. Templates

- `BRIEF-TEMPLATE.md`: added a new section "IF THIS BRIEF CREATES/UPDATES A
  `board/<TICKET-ID>.md` TICKET (required field)" right after the header block, with the
  full taxonomy list and a copy-pasteable metadata-block example.
- `START-SESSION.md`: added a "STANDING RULE, mechanized" bullet to THE LOOP section,
  immediately after the existing BRIEF-TEMPLATE.md bullet, stating the requirement, the
  taxonomy, and pointing at `validate_board.sh`/`capability/assign.py` as the
  enforcement/consumer.

## 4. Backfill — 101 non-parked tickets classified

All 101 `board/*.md` files (every file NOT ending `.md.parked`) got a `work_class:` line.
The 16 true `.md.parked` files were left untouched (exempt from the validator; per the D&S
precedent above, they get `work_class` added at un-park time, same as they already need to
have `depends_on`/`owns` re-confirmed at un-park per several tickets' own "un-park
checklist" notes — e.g. `TIER7B-FOLLOWUP.md`'s own checklist item 3).

Confidence distribution: 65 high, 32 medium, **4 low** (flagged below — please review).
Work-class distribution: greenfield-feature 38, ci-infra 16, bugfix 12, frontend 7,
money-path 7, tests 7, docs 6, routing 4, refactor 3, generalist 1.

**4 LOW-CONFIDENCE — flag for manager review:**
- `BRIDGE-HARDEN` -> `refactor` — hardens the (non-product) session-bridge server; no
  taxonomy class fits a rig-internal infra-hardening ticket cleanly.
- `POOLS-SIMPLIFICATION` -> `refactor` — three plausible classes (refactor / routing /
  money-path), no clean winner; it collapses per-model pools into a sparse-override
  routing scheme built on the DRAIN/cost_rank money-path work.
- `TIER-5` -> `ci-infra` — it's `fleet/claim.sh` (a build-rig script), not an actual CI
  pipeline; `ci-infra` is a stretch but the closest fit in the taxonomy.
- `TIER-6` -> `ci-infra` — same reasoning as TIER-5, for `fleet/fleet-droid.sh`.

Full table (ticket -> work_class -> confidence -> rationale):

| Ticket | Work-Class | Confidence | Rationale |
|---|---|---|---|
| ADR-0015 | `docs` | high | writes ADR + DECISIONS.md register row; no code |
| BRIDGE-HARDEN | `refactor` **LOW** | low | hardens existing session-bridge server behavior; rig-internal infra, no taxonomy class fits cleanly |
| CI1 | `ci-infra` | high | CI_RUNNER var across workflow files |
| CLIENT-CONNECT | `greenfield-feature` | high | new client-connect capability (cli.py+connect.py) |
| CLIENT-CONNECT-GUI | `greenfield-feature` | medium | adds cline+continue to connect registry; new capability, not UI despite name |
| CONSOLE-PROVIDER-MGMT | `frontend` | high | manage providers/models from the web console |
| COST-RANK-AUTO | `money-path` | high | cost_rank auto-derive from pricing, drain priority ordering |
| CWD-CONFIG | `greenfield-feature` | medium | cwd opencode.json renderer for orchestrator agent launch |
| DEP1 | `tests` | medium | adds httpx test dependency; owns pyproject.toml + a test file |
| DOCKER-INSTALL | `ci-infra` | medium | Dockerfile/compose/entrypoint/release scaffolding; borderline vs greenfield-feature |
| DOCS-TWO-MODE | `docs` | high | README + getting-started rewrite, no code |
| DRAIN-ROUTING | `money-path` | high | balance-aware drain routing; ticket's own suggested-agent rationale says money-path |
| DS-PLAN-REVIEW | `docs` | medium | adversarial review doc of the backlog plan; sign-off deliverable, no code |
| DTC-1 | `ci-infra` | high | gate registry + validator tool |
| DTC-2 | `tests` | high | shared HTTP test fixtures |
| DTC-3 | `tests` | high | property-based meta-tests |
| DTC-4 | `ci-infra` | high | unified `charon gate` subcommand + CI wiring |
| DTC-5 | `ci-infra` | high | architecture layer audit gate tool |
| DTC-7 | `ci-infra` | high | automated security audit gate |
| DTC-8-TEST-PATTERNS | `tests` | medium | test-pattern enforcement gate; borderline vs ci-infra |
| E0 | `ci-infra` | medium | engine boundary-guard lint tool (tools/check_boundary.py) |
| E1 | `greenfield-feature` | high | new engine board/claim module |
| E10 | `greenfield-feature` | high | new AIMD capacity module |
| E2 | `greenfield-feature` | high | new engine scheduler module |
| E3 | `greenfield-feature` | high | new engine scanner matrix module |
| E4 | `greenfield-feature` | high | new intake phase1 module |
| E6 | `greenfield-feature` | high | engine integration (cli/validate e2e) |
| E7 | `docs` | high | engine docs, owns only README.md |
| E8 | `greenfield-feature` | high | new auto-land module |
| E9 | `greenfield-feature` | high | new intake phase2 module |
| FALLBACK-PROVIDER | `routing` | medium | default fallback provider chain on failure; routing not cost calc |
| FB1 | `bugfix` | high | fixes boundary-guard relative-import bug |
| FB3 | `refactor` | medium | review-log fragment tooling (splits a growing doc) |
| FB4 | `bugfix` | high | fixes engine concurrency (fenced reclaim primitive) |
| FB5 | `ci-infra` | high | CI hardening across workflow files |
| FB6 | `ci-infra` | high | decisions-lint gate + CI wiring |
| FR1 | `bugfix` | medium | first-run polish fixes |
| FRAGILITY-TICKETS | `docs` | medium | self-described documentation/ticket-creation task, not a build |
| GPT5-POOL-REORDER | `routing` | medium | live pool member reorder; immediate mitigation, config not code |
| GUI-SVELTE-BUILD | `frontend` | high | Svelte/Vite GUI rebuild of the web console |
| HANDOFF-PIPEFAIL | `bugfix` | medium | fixes pipefail-masking bug in handoff.sh (build-rig script) |
| HARD1 | `tests` | high | adds a regression-guard test only |
| INC-401-FAILOVER | `bugfix` | high | explicit incident bug fix (401 misclassification) |
| INTAKE1 | `greenfield-feature` | high | new intake-import capability |
| MODEL-DISCOVERY | `greenfield-feature` | medium | enrich /v1/models metadata, new capability |
| N1 | `greenfield-feature` | high | new per-unit-worktree engine capability |
| N2 | `greenfield-feature` | high | new charon-land capability |
| N4 | `greenfield-feature` | high | new validator/decompose capability |
| N5 | `ci-infra` | high | windows-exe packaging/build workflow |
| OBS-CAPTURE | `greenfield-feature` | medium | persist per-unit agent transcript, new capability |
| OBS-UI | `frontend` | high | read-only work/board panel in the gateway console |
| ORCH-ROUTE | `routing` | high | orchestrator agent-launch routing |
| POOLS-SIMPLIFICATION | `refactor` **LOW** | low | collapses 50 hand-maintained pools to sparse overrides; three plausible classes (refactor/routing/money-path), no clean winner |
| PREFLIGHT | `generalist` | high | manual operator step (charon setup), no code/build; no taxonomy class fits |
| PROD-INSTALL | `greenfield-feature` | medium | install.sh + doctor.py new capability; borderline vs ci-infra |
| PUBLIC-CLEAN-LINT | `ci-infra` | high | hard-gate lint for public-repo leaks |
| RELEASE-SMOKE-FIX | `ci-infra` | high | release.yml smoke-test fix, CI/release pipeline |
| REQUEST-NORMALIZER | `bugfix` | medium | fixes known cross-provider multi-turn request bug |
| RFL-1 | `greenfield-feature` | high | new proactive quota-tracking capability |
| RFL-2 | `frontend` | high | new /chat playground console page (HTML/JS UI) |
| RFL-3 | `routing` | high | image-aware routing exclusion in failover loop |
| RFL-4 | `frontend` | medium | inline limit editor UI in the console |
| RFL-5 | `greenfield-feature` | high | new context-compaction module, opt-in |
| S1 | `greenfield-feature` | medium | new sandbox-policy capability |
| SECRET-SCAN-ENVVAR-FP | `bugfix` | high | fixes land-gate false positive on env-var bearer headers |
| SETUP-KEY-UX | `bugfix` | medium | setup silently accepted a bad key; adds validation |
| SETUP-UX-A | `bugfix` | medium | bundles three first-run setup-UX fixes |
| SR-1 | `money-path` | high | P0 fix for namespaced-id false-downgrade double-bill |
| SR-10 | `ci-infra` | high | deploy hygiene single-producer rule across compose/release/Dockerfile |
| SR-11 | `ci-infra` | high | Dependabot SHA-pin bumps for Actions |
| SR-13 | `frontend` | medium | session-login page for the web console; also touches cli.py |
| SR-2 | `money-path` | high | serves genuine downgrades instead of discard-and-rebill |
| SR-3 | `bugfix` | medium | cache correctness fix + hit/miss counters |
| SR-4 | `docs` | high | doc-only correction to SMART-ROUTING.md |
| SR-5 | `money-path` | high | captures per-token pricing on discovered/imported models |
| SR-5b | `money-path` | high | computes real cost_usd from pricing; money-path multiply |
| SR-6 | `greenfield-feature` | medium | new Anthropic prompt-cache capability, Phase-1 |
| SR-7 | `money-path` | high | spend-cap hardening on estimated cost |
| SR-8 | `greenfield-feature` | medium | wires 6 previously-inert modules into the live path |
| T7 | `greenfield-feature` | high | new L3 unattended autonomy capability |
| T8 | `greenfield-feature` | high | new consensus-breaker reviewer/failover adapters |
| TEST-PORT-FLAKE | `tests` | high | explicit CI robustness/test-only ephemeral-port fix |
| TIER-1 | `greenfield-feature` | high | new tier config store |
| TIER-2 | `greenfield-feature` | high | new gateway tier pools |
| TIER-3 | `greenfield-feature` | high | new CLI tier support |
| TIER-4 | `frontend` | medium | tier web UI in the setup console |
| TIER-5 | `ci-infra` **LOW** | low | fleet claim.sh tier support; a build-rig script, not a CI pipeline — taxonomy stretch |
| TIER-6 | `ci-infra` **LOW** | low | fleet-droid.sh tier launch support; a build-rig script, not a CI pipeline — taxonomy stretch |
| TIER-7 | `greenfield-feature` | high | agnostic tier routing across agent_launch/api/acp |
| TIER-SELECT | `greenfield-feature` | medium | curated model catalog + CLI/web picker; hybrid, leans feature over pure UI |
| TIER7B | `greenfield-feature` | high | tier phase-B multitier routing capability |
| TIER7B-FOLLOWUP | `tests` | medium | regression test + small hardening follow-up |
| TOOL-REPAIR-MUTATING | `bugfix` | high | allow_mutating flag is a no-op; explicit bug fix |
| WCI | `greenfield-feature` | high | WCI MVP static reconciler + depth pre-sort, new engine capability |
| WCI-FOLLOWON | `greenfield-feature` | high | new semantic-proof engine capability |
| WORK-AGENT-BEARINGS | `greenfield-feature` | medium | new intake/api/acp bearings capability |
| WORK-BEARINGS-WORKPATH | `greenfield-feature` | medium | new work-bearings workpath, builds on LAND-PR runner |
| WORK-GATEWAY-WIRE | `greenfield-feature` | medium | new agent-launch gateway-credential wiring |
| WORK-LAND-PR | `greenfield-feature` | high | new land-PR capability (cli/land.py/review adapter) |
| WORK-OBSERVABILITY | `greenfield-feature` | medium | new scheduler/cli observability capability |
| WORKTREE-ADD-FORCE | `bugfix` | high | fixes add_worktree --detach aborting on stale registration |

## 5. `capability/assign.py` wiring

**No code change was needed.** Grounding `assign.py` showed its `read_ticket_meta()`
(generic `key: value` regex reader) already did `work_class = work_class or
meta.get("work_class")` (line ~219) and, when that came back `None`, already printed a
clear NOTE and fell back to `generalist` (defensive default, existing code, not new). The
module's own docstring calls it "the shared capability brain" built ahead of the ticket
schema landing — this build is exactly that landing. Once the field existed with the exact
key `work_class` (chosen deliberately to match, see §1), `assign.py` started auto-resolving
it with zero further changes. Confirmed live (see §6).

## 6. Verification

**Check A — validate_board.sh over the real (backfilled) board:**
```
$ bash validate_board.sh 2>&1 | grep -c "work-class"
0
```
Exit code is still 1, but for 5 PRE-EXISTING, unrelated reds (confirmed present
before any of this session's edits, via `git stash` + re-run of the original
`validate_board.sh` against the original board — identical 5 reds, same messages):
```
RED  missing-prompt: GUI-SVELTE-BUILD -> /home/stack/charon-private/prompts/gui-svelte-build.md
RED  owns-collision LIVE (no dep ordering): Dockerfile <- GUI-SVELTE-BUILD SR-10 [...]
RED  owns-collision LIVE (no dep ordering): src/charon/config.py <- COST-RANK-AUTO DRAIN-ROUTING GUI-SVELTE-BUILD POOLS-SIMPLIFICATION [...]
RED  owns-collision LIVE (no dep ordering): src/charon/gateway.py <- COST-RANK-AUTO DRAIN-ROUTING GUI-SVELTE-BUILD POOLS-SIMPLIFICATION [...]
RED  owns-collision LIVE (no dep ordering): src/charon/proxy_server.py <- DRAIN-ROUTING GUI-SVELTE-BUILD INC-401-FAILOVER RFL-2 RFL-3 RFL-4 SR-13 SR-6 [...]
```
These are unrelated to work_class (a missing prompt file + real owns collisions around
`GUI-SVELTE-BUILD`) — flagged here, not fixed (out of this ticket's scope; per
`memory: never-ignore-preexisting-issues`, surfacing rather than silently dismissing).
**work_class itself is fully GREEN across all 101 tickets.**

**Check B — negative tests (created in `board/`, deleted immediately after):**
`board/TEST-WC-MISSING.md` (all fields except `work_class`) and
`board/TEST-WC-INVALID.md` (`work_class: not-a-real-class`) — `validate_board.sh` cannot be
pointed at an arbitrary directory (its `FLEET` var is derived from the script's own
location, not a CLI arg), so the throwaway tickets were created directly in `board/`,
verified, then `rm`'d (confirmed gone via `git status` — no stray files left).
```
RED  work-class-invalid: TEST-WC-INVALID work_class 'not-a-real-class' is not one of bugfix, ci-infra, docs, frontend, generalist, greenfield-feature, money-path, refactor, routing, tests
RED  work-class-missing: TEST-WC-MISSING has no 'work_class:' field (required — one of: bugfix, ci-infra, docs, frontend, generalist, greenfield-feature, money-path, refactor, routing, tests)
```
Both FAILED as expected, with a clear, ticket-identifying message. PASS.

**Check C — assign.sh auto-resolving work_class with no `--work-class` flag:**
```
$ bash assign.sh SR-1
TICKET: SR-1
PICK: glm-5.2  (work_class=money-path)
  glm-5.2: n=1 merge=100% block=0% score=-59 [LOW-CONFIDENCE: n<4] cost=$0.0088 time=23.2s
  tier=med
  availability=unknown
  runner-up: kimi-k2.6: n=1 merge=100% block=0% score=-59 [LOW-CONFIDENCE: n<4] cost=$0.0138 time=82.3s

$ bash assign.sh DTC-2
TICKET: DTC-2
PICK: kimi-k2.6  (work_class=tests)
  kimi-k2.6: n=7 merge=86% block=0% score=13 (no tests data — generalist fallback) cost=$0.0086 time=46.9s
  tier=med
  availability=unknown
  runner-up: gpt-5.4: n=7 merge=86% block=0% score=13 (no tests data — generalist fallback) cost=$0.0810 time=23.3s
```
Both correctly resolved `work_class` (`money-path`, `tests`) straight from the ticket file
— no `--work-class` flag passed, no "NOTE: ticket declares no work_class" fallback message.
PASS. Also re-ran `capability/selftest.py` as a cheap regression check (not required by the
brief, but free): still `SELFTEST: ALL CHECKS PASS`.

## 7. Proposed commit message (NOT committed — operator's call)

```
fleet: require work_class on every board ticket; wire to assign.py

Add a work_class: field (capability/grades.py's WORK_CLASSES + generalist)
next to tier: on every live board ticket, matching the existing single-line
metadata convention. validate_board.sh now hard-fails a ticket missing the
field or using an off-taxonomy value, following the same *.md-glob-exempts-
.md.parked precedent the D&S standing-rule check already established.
Backfilled all 101 non-parked tickets by reading each ticket's scope/owns/
branch (4 flagged low-confidence for manager review: BRIDGE-HARDEN,
POOLS-SIMPLIFICATION, TIER-5, TIER-6). capability/assign.py already read
meta.get("work_class") ahead of the schema landing, so no code change was
needed there -- it now auto-resolves the best model per ticket without a
manual --work-class flag. Updated BRIEF-TEMPLATE.md and START-SESSION.md so
new tickets carry the field from creation.
```
