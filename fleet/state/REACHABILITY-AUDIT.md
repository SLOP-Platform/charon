# REACHABILITY AUDIT — hardcoded cross-boundary paths

Ticket: `fleet/board/REACHABILITY-GATE.md`. Analysis + design only — no product/rig code
changed. Confirmed root instance (MODEL-PREFLIGHT wall): `fleet/benchmark/grader-daemon.py`
hardcodes `/home/stack/...` that `bench-grader` (uid 999, not in group `stack`) cannot
traverse (`/home/stack` is `drwxr-x--- stack:stack`).

## Code-map tool: FOUND and USED — `graphify`

The operator's "code map app" is **graphify** (`/home/stack/.local/bin/graphify`, a `uv tool`
install of `graphifyy`), already integrated into KSF (`ksf module add graphify` →
`ksf/modules/graph_adapter/`, see `fleet/state/overnight/KS3-GRAPHIFY-REPORT.md`). It builds
an AST-derived structural graph (`graphify-out/graph.json`: nodes = functions/classes/
modules/imports, edges = call/import relationships).

**Used it**: ran `graphify update . --no-cluster` against `/home/stack/code/charon`
(5832 nodes, 12698 edges, no LLM calls). Queried `graph.json`'s `source_file` field across
all 5832 nodes — every node's source file resolves under `tests/`, `src/`, `docs/`, `tools/`,
`.opencode/`, `packaging/`, or repo-root docs; **zero nodes point outside the product repo
(no `fleet/`, no `/home/stack/charon-private` path appears)**. This structurally confirms the
product-vs-rig import boundary (d) at the AST level: nothing in `src/charon` imports rig code.
(Generated `graphify-out/` was deleted after use — analysis-only, no tree changes.)

**Limitation (documented honestly)**: graphify's node schema is
`{id, label, file_type, source_file, source_location, ecosystem, metadata, _origin}` — it
captures code **structure**, not string-literal **content**. `grep -c "/home/stack"
graph.json` → 0, even though grep-on-source finds real hits (e.g.
`tools/check_public_clean.py:22`). So graphify cannot itself enumerate hardcoded path
*strings* — the actual defect class here. Per the ticket's own instruction ("use the code
map... PLUS grep"), the literal-path enumeration below was done by grep; graphify supplied
the structural cross-repo-import sanity check.

---

## PART 1 — Audit matrix (ranked, file:line cited)

### CRITICAL — confirmed broken today (boundary a: different unix user)

| File:line | Literal | Writer | Reader | Why unreachable |
|---|---|---|---|---|
| `fleet/benchmark/grader-daemon.py:42` | `FLEET_DIR = Path("/home/stack/charon-private/fleet")` | bench-grader daemon process | same daemon (writes `SCORECARD_TSV`, `scorecard.v{n}.json` at `FLEET_DIR`) | No env override, no runtime user-check. `/home/stack` is `drwxr-x--- stack:stack` — bench-grader (uid 999, not in `stack` group) cannot traverse into it at all, independent of whether the literal string is "correct." **This is the ticket's confirmed root instance.** |
| `fleet/benchmark/deploy-preflight-graders.sh` (whole file) | none literal — uses `$here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` (already the CORRECT pattern) | n/a | n/a | Well-written internally, but **the file's own location** is under `/home/stack/charon-private/fleet/benchmark/`. `sudo -u bench-grader .../deploy-preflight-graders.sh` cannot even `cd`/exec it — the topology itself is unreachable. A pure rewrite of internal path logic cannot fix this; the fix is deployment topology (copy-then-run, a shared-readable staging path, or an ACL grant on a narrow subtree). Flag as CRITICAL / distinct sub-class: "correct script, unreachable location." |

### HIGH — latent (same class, not yet exercised across the boundary, but zero portability)

| File:line | Literal | Writer/Reader | Boundary | Risk |
|---|---|---|---|---|
| `fleet/checks/bridge-health.py:11,23` | `BRIDGE_SOCKET = "/home/stack/.charon/bridge.sock"`; `subprocess.run(["python3", "/home/stack/.config/opencode/session-bridge/proxy.py"], ...)` | script sets/execs | (a)/(c) | Hardcoded to user `stack`'s home. Invoked today only by `stack` (via `preflight.sh`, `reds.tsv` verify-commands) so it's currently latent, but any run under a different account silently fails to find `proxy.py`. |
| `fleet/capability/availability.py:24` | `PROXY_PATH = "/home/stack/.config/opencode/session-bridge/proxy.py"` | routing-influencing capability engine | (a)/(c) | Same pattern, feeds the `assign()` routing decision — higher blast radius than a standalone check. |
| `fleet/capability/grades.py:442` | `_CHARON_SRC = Path("/home/stack/code/charon/src")` | dynamic `sys.path.insert` to import `charon.model_catalog` for tier-alias resolution | (c) | Has a documented local-fallback alias table if the import fails — graceful degrade exists, but it's an **undocumented silent drift risk**: if `src/charon/config.py`'s `TIER_ALIASES` changes, the hardcoded fallback can go stale with the primary path never even resolving on a second host, and nothing flags that it didn't. |

### MEDIUM — rig-internal, single-operator scripts (capped severity: per `[[product-vs-build-rig-boundary]]` the rig never ships, but boundary (c) fresh-install/second-host is still broken)

**Bad pattern — bare literal, no override, no script-relative resolution:**
`fleet/checkin.sh:24`, `fleet/next.sh:23-24`, `fleet/summary.sh:28,115-117`,
`fleet/preflight.sh:134`, `fleet/retire-done.sh:57`, `fleet/fleet-droid.sh:19`,
`fleet/handoff.sh:16-17,66-67,117,127,133,138,144,146,157,159,188`,
`fleet/handoff-check.sh:8,91,101,110`, `fleet/land.sh:9,87`,
`fleet/land-push.sh:10,17`, `fleet/repo-registry.sh:5,36-37,43-44,52-53`.

**Good pattern already — env-override-with-default (the target contract, working):**
`fleet/_lib.sh:43`, `fleet/reconcile-merged.sh:23`, `fleet/project-audit.sh:18`,
`fleet/decompose.sh:29`, `fleet/done.sh:19`, `fleet/deploy-session-end.sh:8`,
`fleet/branch-reaper.sh:38`, `fleet/sync-checkouts.sh:36-37`, `fleet/charon-run.sh:13`,
`fleet/benchmark/graders/preflight_checks/dedupe-provider-list.py:19` — all use
`${VAR:-/home/stack/...}`. These are **not violations**; they demonstrate the correct
pattern and are allowlist candidates (see PART 3).

### LOW — data/doc/self-referential (not fragile live-code paths)

| Location | Why low |
|---|---|
| `fleet/benchmark/graders/preflight_checks/_pf_common.py:242`, `add-provider-config.py:7`, `benchmark/preflight-tasks/manifest.tsv:32,40` | These ARE the secret-hygiene grader's own detection pattern/spec text (it exists specifically to catch `/home/stack` leaks in model output) — correctly self-referential, not fragility. |
| `fleet/reds.tsv:9-13`, `fleet/waves/smart-routing.json:90,130` | Historical ledger/data rows (past verify-commands, file lists) — documentary, not executable path resolution. |
| `fleet/benchmark/selftest/session_cost_selftest.py:46-47`, `benchmark/selftest/test_grader_daemon.py:162` | Dev-only selftest fixtures pinned to the known dev box; never run outside a dev shell today. |
| `tools/check_public_clean.py:22`, `tools/.public-clean-exceptions.json`, `tests/test_public_clean.py:85,262` (product repo) | The public-clean lint's own regex pattern + its test fixtures/exceptions ledger — necessarily contain the string they detect. |

### Product-vs-rig boundary (d) — CONFIRMED CLEAN

`grep -rn "/home/stack" src tools tests` in `/home/stack/code/charon` returns **only** the
lint's own pattern (`tools/check_public_clean.py:22`) and its fixtures/exceptions
(`tools/.public-clean-exceptions.json`, `tests/test_public_clean.py`). The two `fleet/`
mentions in `src/charon/lifecycle.py` and `src/charon/capability/scorecard.py` are
**docstring prose** pointing at the rig conceptually (`"fleet/benchmark/preflight.sh"` as a
comment), not file reads — confirmed by (1) `tools/check_no_rig_import.py`, an existing
AST-level import guard that already bans `import benchmark`/`import grader_daemon` on the
product hot path, and (2) manually tracing `ScorecardStore`'s path resolution:
`src/charon/lifecycle.py:319` → `base = config_dir if config_dir is not None else
secrets.config_dir()` → honors `$CHARON_HOME`, never a hardcoded rig path. Also confirmed via
graphify (see above): zero graph nodes point outside the product repo.

### Deploy-drift boundary (b) source-tree vs `/data` volume — CONFIRMED CLEAN (already fixed)

`Dockerfile` declares `/data` as a `VOLUME`, `ENV CHARON_HOME=/data`; `docker-compose.yml`
sets `CHARON_HOME=/data` and `CHARON_STATE_DIR=/data` explicitly (with an in-file comment
explaining why leaving `CHARON_STATE_DIR` at its `/work/.charon` image-default would wipe
state on redeploy); `fleet/deploy.sh`'s `KEY_CHECK_PY` reads `CHARON_STATE_DIR` (default
`/data`) and derives required keys from the live `pools.json`/`tiers.json`/`models.json`
rather than a hand list. Matches `[[charon-deploy-drift-lessons]]` (already resolved
2026-07-03). **No new violations found in this boundary.**

### Adjacent finding — NOT a hardcoded-path defect, but directly gates whether PART 3 will fire

`src/charon/gate_runner.py`'s `CHECKS` list (the list actually executed by
`python3 -m charon.cli gate`, which is what CI's `ci.yml` runs) is **narrower** than
`tools/gates.json`'s registry. `tools/check_no_rig_import.py`, `check_arch.py`,
`check_security.py`, `check_test_patterns.py`, `check_workflows.py` are all **registered**
in `gates.json` but **none of them appear in `gate_runner.py`'s `CHECKS` list or in
`.github/workflows/ci.yml`** — they are registered gates that do not actually execute today.
This is a live instance of `[[gates-must-actually-run]]`. It matters directly for PART 3:
registering a new `no-unreachable-paths` gate in `gates.json` is **not sufficient** — it must
also be added to `gate_runner.py`'s `CHECKS` list, or it will silently never run, exactly like
these five.

---

## PART 2 — Root cause

1. **Single-operator `/home/stack` dev-box assumption baked in at authorship time.** Every
   rig script was written when there was exactly one operator, one host, one clone location.
   The literals were never wrong until a second actor (`bench-grader`) or a second host
   (fresh install, a backup box) entered the picture.
2. **Boundaries were retrofitted AFTER the paths already existed.** `bench-grader` isolation
   was added on top of an already-hardcoded `grader-daemon.py`; the `/data` volume boundary
   was added on top of a codebase that once ran bare; the public-repo/product-ships-standalone
   boundary was added on top of a codebase that started as one shared tree. Nothing forced a
   retroactive path audit when each boundary landed.
3. **No portability contract existed** until `check_public_clean.py` (blocks `/home/stack`,
   `charon-private`, internal IPs in the *product* repo) and `check_no_rig_import.py`
   (blocks rig imports on the *product* hot path) — good precedent, but **rig-side (`fleet/`)
   has zero equivalent enforcement**, hence the ~30 bare-literal hits found today.
4. **Even where a gate exists, it doesn't always run** (see Adjacent finding above) — a
   "green" gate registry entry proves nothing if it never executes (`[[gates-must-actually-run]]`).

### Contract, going forward

Any path that crosses a boundary (different unix user, container/volume, fresh host,
product-vs-rig) **must** be resolved from config/env at runtime — **never** a bare string
literal to a dev-box location. Resolution order, in the order the codebase already
demonstrates correctly in places:

1. **Hard cross-user boundary** (e.g. `bench-grader`): an explicit env var with **no** default,
   plus a runtime `id -un` self-check that refuses to proceed as the wrong user — exactly
   `deploy-preflight-graders.sh`'s existing `KEYS` + `me="$(id -un)"` guard. `grader-daemon.py`
   needs this pattern for `FLEET_DIR`/`SCORECARD_TSV` and does not have it today.
2. **Single-operator convenience default**: `${VAR:-/home/stack/...}` — override-with-default,
   already used correctly by `_lib.sh`, `reconcile-merged.sh`, `project-audit.sh`,
   `decompose.sh`, `done.sh`, `deploy-session-end.sh`, `branch-reaper.sh`,
   `sync-checkouts.sh`, `charon-run.sh`, `dedupe-provider-list.py`.
3. **Ships-with-its-own-tree**: script-relative resolution,
   `$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)` — already used correctly by
   `deploy-preflight-graders.sh` and `gate.sh`.
4. **Product-side persistent state**: `CHARON_HOME`/`CHARON_STATE_DIR` via
   `secrets.config_dir()` — already the enforced pattern in `src/charon`, confirmed clean.

A boundary is never "safe because it's rig-only" — a rig script that assumes
single-operator/single-host still rots the moment there's a second box or a second operator.
Keep even MEDIUM-severity rig scripts on pattern 2 or 3, not a bare literal.

---

## PART 3 — Gate design (spec only, NOT built)

`fleet/checks/no-unreachable-paths.sh`

**What it flags** (line-based regex scan, mirroring `check_public_clean.py`'s proven
line-content-keyed approach for auditability):
- `/home/stack\b` — the confirmed dev-box home.
- `/home/(?!bench-grader\b)[A-Za-z0-9_.-]+` — any *other* non-self user's home
  (parameterized so bench-grader's own legitimate `/home/bench-grader/keys` doesn't
  false-positive).
- A literal `/data` path (`"/data..."`, `= /data`) appearing **outside** the recognized
  config layer (`src/charon/secrets.py`'s `config_dir()`, `Dockerfile`,
  `docker-compose.yml`) — i.e. any *new* file hardcoding `/data` without routing through
  `CHARON_HOME`/`CHARON_STATE_DIR`.
- Other dev-box absolutes as found (`/var/lib/bench-grader`, etc.) — start narrow, expand
  only as new instances surface; do not over-fit to patterns not yet observed.

**Two severities** (mirrors the audit's own tiering):
- **Product side** (`src/charon`, `tests/`, `tools/`): zero tolerance — any hit is a hard
  FAIL, same posture as `check_no_rig_import.py`.
- **Rig side** (`fleet/`): FAIL only on a **bare literal** — i.e. skip a hit whose line (or
  the immediately preceding declaration) already uses the `${VAR:-...}` override-with-default
  pattern or `$(dirname "${BASH_SOURCE[0]}")` script-relative resolution. The checker must
  recognize both already-good patterns in the codebase, or it will re-flag ~10 files that are
  already compliant and drown the real hits.

**Minimal reasoned allowlist** (derived directly from this audit's LOW-severity findings —
content-keyed like `check_public_clean.py`'s exceptions ledger, i.e. keyed by exact line
content so a *new* bad line in the same file still gets caught, not a blanket per-file skip):
- `tools/check_public_clean.py` (its own pattern), `tools/.public-clean-exceptions.json`,
  `tests/test_public_clean.py` — a lint's own regex/fixtures necessarily contain the string
  it hunts.
- `fleet/benchmark/graders/preflight_checks/_pf_common.py`, `add-provider-config.py`,
  `fleet/benchmark/preflight-tasks/manifest.tsv` — the secret-hygiene grader's own
  detection pattern/spec text.
- `fleet/reds.tsv`, `fleet/waves/smart-routing.json` — historical ledger/data rows.
- `fleet/benchmark/selftest/*.py` — dev-only selftest fixtures.

**Wiring:**
- Rig: mirror the existing `fleet/checks/no-claude-executor.sh` pattern — invoke from
  `preflight.sh` as `$HERE/checks/no-unreachable-paths.sh` (script-relative, so the invoking
  line in `preflight.sh` isn't itself flagged) and add it to `fleet/gate.sh` alongside the
  `*.test.sh` loop.
- Product: register in `tools/gates.json` (new `"reachability"` domain, add it to
  `check_gate_registry.py`'s `ALL_DOMAINS` frozenset) **and** — per the Adjacent finding
  above — add it to `src/charon/gate_runner.py`'s `CHECKS` list. Registering in `gates.json`
  alone is not sufficient; that list is validated for registry consistency, not executed.

**FAIL-ON-REVERT test shape:** a fixture test (`fleet/tests/test_no_unreachable_paths.test.sh`
rig-side, `tests/test_no_unreachable_paths.py` product-side) that:
1. Writes a temp file containing a fresh bare `/home/stack/...` literal outside the
   allowlist → asserts the checker exits non-zero and names `file:line` — mirrors
   `tests/test_public_clean.py`'s existing shape (`f.write_text("cd /home/stack/repo\n")`).
2. Writes a temp file using `${VAR:-/home/stack/...}` and one using
   `$(dirname "${BASH_SOURCE[0]}")` → asserts the checker does **NOT** flag either (proves
   the allowlist-pattern recognition doesn't drown real hits, keeping the gate usable for
   rig scripts that already follow the contract).

Adversarial review before build: confirm the gate actually appears in both
`gate_runner.py`'s `CHECKS` and `fleet/gate.sh`'s invocation path, not just `gates.json` —
that is the exact gap already found live in five other registered-but-unwired gates.
