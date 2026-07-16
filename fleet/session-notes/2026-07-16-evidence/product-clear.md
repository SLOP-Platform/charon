# PRODUCT PR clearing review — 2026-07-16
Repo: SLOP-Platform/charon. READ-ONLY review; manager executes merges.
All claims below verified by running code, not by reading the prior audit.

---

## 0. HEADLINE: priority #1 is already done; priority #2 is a false alarm

1. **#162 is CLOSED, not open.** Superseded by **#168** (merged 07-16 07:13,
   master `72a11d8`), which rebuilt the same work on master w/ #165. The
   operator's Switchboard+Decomposer priority is **already landed**.
2. **#170's "import cycle" is a FALSE POSITIVE manufactured by #170's own tool
   change.** There is no runtime cycle. Proven below. Worse, #170 "fixes" a
   second false positive by degrading product source (SSOT break).
3. **#86 rebase-cures — proven empirically**, not inferred.
4. **#135 is NOT crash-partial** despite its title, and needs a **3-line** fix,
   not "real work" as the prior audit implied.
5. **#164 is a confirmed infra flake** and has NOT been re-run since.

---

## 1. #162 — DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD → NO ACTION (already landed)

`gh pr view 162` → `state: CLOSED, mergedAt: null`, closed 07-16 07:10.
Superseded by #168, merged 07-16 07:13 as master `72a11d8`:

    docs/review-log/DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD.md | 108 ++
    src/charon/decompose_planner.py                         | 535 +++---
    src/charon/recommend.py                                 |   4 +-
    tests/test_decompose_planner.py                         | 611 +++---

**Verified the rebuild did not drop #162's extra guard commit.** #162's branch
carried `59da7b1 test(switchboard): drive production _switchboard_routes for
never-Anthropic guard`. That test **survives on master**:

- Guard (production): `src/charon/decompose_planner.py:332-337` — drops any
  route where `"anthropic" in provider`, `"anthropic" in upstream_base`, or
  `mid.startswith("claude")`.
- FAIL-ON-REVERT test: `tests/test_decompose_planner.py:348`
  `test_switchboard_routes_drops_anthropic_route` — drives the REAL
  `_switchboard_routes`; goes RED if the guard is cut.

No coverage lost. Closing #162 was correct.

### ⚠️ FLAG FOR OPERATOR (already on master — not a merge decision)
`src/charon/decompose_planner.py:282-283` and `:332-334` assert the
never-Anthropic rule is **PLANNER-ONLY**:

> "drop Anthropic (SG-never-Anthropic is a planner-only invariant — **the
> gateway's tier-voter is allowed Anthropic**)"

The standing HARD RULE as briefed is "the **gateway** must NEVER route to
Anthropic". Code now encodes a narrower rule and says the gateway tier-voter
MAY use Anthropic. Either the rule was deliberately narrowed (needs an explicit
operator confirm per `adversarial-review-must-not-silently-override-operator`)
or this is a silent scope reduction that landed in #168. **Worth one question.**

---

## 2. #170 — API-DECOMPOSE-CYCLE-FIX → **NEEDS-WORK** (red is SELF-INFLICTED)

### Reproduced exactly
Worktree on `origin/feat/api-decompose-cycle-fix`, ran `tools/check_arch.py`:

    arch: 1 violation(s)
      [circular imports] circular-import: charon.config → charon.config.keyprobe → charon.providers → charon.config

### Root cause: the checker counts DEFERRED imports as module-level edges
`tools/check_arch.py` `_scan_module_level_imports` iterates **`ast.walk(tree)`**
(branch, ~line 291) — which descends into function bodies. Its own name says
*module-level*; its own docstring says it returns *"module-level charon import
edges"* matching *"the same edges the import system actually executes"*. It does
neither: it only excludes `if TYPE_CHECKING:` blocks, not function bodies.

The two edges that close the reported cycle are **both deferred**:

- `src/charon/config/keyprobe.py:41` — `from .. import providers`
  (inside a function body).
- `src/charon/providers.py:260` — `from . import config` — carrying the literal
  comment: **`# deferred: config has no reverse dependency on this module,`**
  `# but keep the import local to this rarely-hit fallback branch rather than`
  `# module-level.`

Only `src/charon/config/__init__.py:32` (`from .keyprobe import (...)`) is a real
module-level edge. A cycle needs all three; two are deferred → **no cycle**.

**#170's per-alias change is what surfaces it.** Its `_resolve_import_target`
rewrite makes `from . import a, b` yield one edge per alias instead of collapsing
to the parent package. That change is *correct in isolation*, but applied through
an `ast.walk` scanner it converts the standard deferred cycle-break idiom into a
reported cycle.

### Proof there is no runtime cycle
    python3 -c "import charon.config"   →  IMPORTS FINE — no runtime cycle
Master's own `check_arch.py` → `arch OK`.

### The api↔decompose cycle #170 "fixes" is ALSO a false positive
- `src/charon/decompose.py:30` — `from . import api, gitutil` → module-level (real).
- `src/charon/api.py:269` — `from .decompose import run_decomposed` → **deferred**.
- `src/charon/api.py:320` — `from .decompose import decompose as _decompose_stages` → **deferred**.

Both return edges are deferred → never a runtime cycle either.

### #170's src "fix" degrades product code (SSOT break)
`git diff origin/master...origin/feat/api-decompose-cycle-fix -- src/` is 2 lines:

    -from . import api, gitutil
    +from . import gitutil
    ...
    -    state_dir: str = api.DEFAULT_STATE_DIR,
    +    state_dir: str = ".charon",

It hardcodes the constant to silence a checker bug. `api.py:32` is
`DEFAULT_STATE_DIR = ".charon"` so **no behaviour change today**, but it forks
the SSOT: 8 other call sites still reference `api.DEFAULT_STATE_DIR` —
`parallel.py:197`, `cli.py:1375,1430,1854,1907,1952,1958,2004`. `decompose.py`
becomes the lone divergent default; any future change to the constant silently
skips it. This is the `always-fix-catalog-mismatches` class, introduced (not
fixed) by this PR.

### PROVEN CORRECT FIX (one scanner change; zero product-source change)
Patched #170's `_scan_module_level_imports` to skip `FunctionDef`/
`AsyncFunctionDef` bodies (honouring its own contract), kept its per-alias fix,
and ran it against **pure master src with no source changes at all**:

    arch OK: no layer-isolation, circular-import, stdlib-only, or vendor-name violations under src/

Both "cycles" vanish with no product edit. So #170 should:
1. Restrict the scan to import-time nodes (skip function bodies).
2. **Revert the `decompose.py` change entirely** — restore
   `from . import api, gitutil` and `state_dir: str = api.DEFAULT_STATE_DIR`.
3. Keep the per-alias `_resolve_import_target` fix (genuine value).

Optionally add a regression test asserting a deferred import is NOT a graph edge.

**Order-critical**: `gate` is a required check. Once merged it red-lines any
branch with a latent cycle — but as written it would also red-line every
legitimate deferred cycle-break in the codebase. Merge LAST, only after the
scanner fix.

---

## 3. #164 — CAPABILITY-ACTUALS-DEADREF-CLEANUP → **MERGE-READY after CI re-run**

Current gate FAILURE (run 29477132244, completed 06:36:04) — job log:

    [pytest] FAILED (exit 1)
    ERROR at setup of test_autonomous_run_wires_to_real_engine
    E   FileNotFoundError: [Errno 2] No such file or directory: '/tmp/pytest-of-stack/pytest-53'
        pytest_asyncio/plugin.py:924: FileNotFoundError
    ERROR at setup of test_clean_file_has_no_violations
    E   FileNotFoundError: ... '/tmp/pytest-of-stack/pytest-53'

**Confirmed INFRA FLAKE**, not #164's code: failures are at `tmp_path` fixture
*setup*, in `pytest_asyncio`'s plugin, on tests unrelated to the diff. The
self-hosted runner reaped its pytest tmp dir mid-run. **This is still the same
run the prior audit saw — #164 has NOT been re-run.** Re-run before any code
change; do not debug.

Mildly order-critical: edits `tools/check_inert_code.py` + disposition json
(changes inert-code gate surface). Merge after the re-run, before #170.

---

## 4. #135 — FT-CATALOG-SEED → **NEEDS-WORK, 3-line fix** (NOT crash-partial)

Title says *"launcher auto-commit — droid exited without committing (review for
completeness)"* → judged from the DIFF per the crash-partial rule.

**Verdict: COMPLETE.** +489 lines across every file in the ticket's `owns:`:

    docs/review-log/FT-CATALOG-SEED.md             |  98 ++
    src/charon/provider_presets/hosted.py          |  22 ++
    src/charon/routing_policy/free_tier_catalog.py | 189 ++ (NEW)
    tests/test_free_tier_catalog.py                | 180 ++

Presets match the ticket's `accept:` exactly — `github_models`
(`https://models.inference.ai.azure.com`, `GITHUB_TOKEN`), `featherless`
(`max_context: 32768` for the 32K cap), `ollama_cloud` (`https://ollama.com/v1`,
distinct from the LOCAL ollama preset, which is untouched). Its own tests:
**16 passed**. `check_arch` and `check_public_clean` both OK on the branch.

### HARD-RULE: compliant and exemplary
18 `anthropic|claude` hits in the diff are all **negative guards**, e.g.
`test_no_anthropic_entry_in_seed`, `assert "anthropic" not in FREE_TIER_CATALOG`,
plus a fail-loud guard forcing any future Anthropic entry to be explicit. No
Anthropic provider is added anywhere.

### The genuine red, and its exact fix
`tests/test_provider_response_contract.py:131` raises for presets with no
declared raw-shape fixture — #135 seeds 3 new presets without declaring them.
That file is **outside #135's `owns:`**, which is why the droid didn't touch it.
All three are OpenAI-compatible (per their own preset notes), so the fix is to
add them to `_OPENAI_SHAPE_PRESETS` (`tests/test_provider_response_contract.py:88`).

**Empirically verified** — added `"featherless", "github_models", "ollama_cloud"`
to that frozenset and ran the contract suite:

    29 passed, 1 xfailed, 1 xpassed in 16.81s

Unblocks FT-WIRE-QUOTA — but it is **1 of 7** prerequisites, so no quick unblock.

---

## 5. #169 / #161 / #166 — docs fragments

- **#166 — MERGE-READY.** `gate` SUCCESS + `wheel-smoke` SUCCESS (verified
  07-16 07:00). Docs-only, single file, 40 insertions,
  `docs/review-log/STARTUP-CONTEXT-DIET.md`. No collisions. Safest merge.
- **#169 — NEEDS-WORK.** Genuine, self-inflicted public-clean violation; 3 leaks:
  - `docs/CHARON-FLOWCHART.md:369` — `/home/stack/charon-private/fleet/`
  - `docs/review-log/CHARON-FLOWCHART.md:562` — `/home/stack/charon-private/fleet/`
  - `docs/review-log/CHARON-FLOWCHART.md:644` — `/home/stack/.local/share/opencode/tool-output/tool_f69c83df...`
    (leaks a private opencode tool-output path — worst of the three)
  Repo is PUBLIC. Trivial fix; must not land as-is.
- **#161 — NEEDS-WORK.** One leak: `docs/review-log/WEB-ROADMAP-GENERATOR.md:11`
  references `charon-private/fleet/roadmap-html.sh`. One line. Trivial.
  (Diff is docs-only, 16 insertions — despite the PR title claiming it "wires
  end-session.sh"; the actual wiring is rig-side, not in this product PR.)

---

## 6. #86 — dependabot → **MERGE-READY after rebase, no code change** (PROVEN)

Not inferred — tested. Took a clean `origin/master` worktree, overwrote its four
workflow files with **#86's exact versions**, ran master's checker:

    public-clean OK: no personal/internal patterns found in tracked files

Master `0a962dc` (07-15) added `_ACTION_SHA_PIN_RE` to
`tools/check_public_clean.py`, which whitelists 40-hex SHA pins in the `uses:`
slot under `.github/workflows/` (and only there). #86's last CI ran **07-13**,
two days before that fix. **Strand victim confirmed: rebase → green.**

---

## 7. Collisions

Prior audit's claim re-verified: **zero file collisions across all product PRs.**
Order is driven purely by red/green and gate-tightening, not contention. The one
sequencing constraint is #164 and #170 both being gate-surface changes.

---

## 8. RECOMMENDED MERGE SEQUENCE

1. **#166** — green now, docs-only. Merge immediately.
2. **#86** — rebase onto master, re-run. No code change. (Proven.)
3. **#161** — strip `charon-private` from 1 line.
4. **#169** — strip `/home/stack` ×3 (incl. the opencode tool-output path).
5. **#164** — re-run the flaked job first; only debug if it fails a 2nd time.
6. **#135** — add 3 names to `_OPENAI_SHAPE_PRESETS`. (Proven 3-line fix.)
7. **#170 — LAST, and only after rework**: fix the scanner to skip function
   bodies, revert the `decompose.py` SSOT break, keep the per-alias fix.

#162: no action — already landed via #168.
