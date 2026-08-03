# BDD-FRAMEWORK-EVAL — Behaviour-Driven Development Framework Evaluation

**Date:** 2026-08-02
**Ticket:** BDD-FRAMEWORK-EVAL (tier: frontier, priority: 0, difficulty: 4)
**Branch:** eval/bdd-framework

## VERDICT

**DO NOT ADOPT — plain pytest with disciplined given/when/then naming wins.**

BDD frameworks (pytest-bdd, behave) add a second artifact (`.feature` gherkin) that must
be kept in sync with code. In a rig where agents write the code and a human reviews outcomes,
this is a work MULTIPLIER — every behaviour change requires updating TWO artifacts correctly.
Plain pytest with docstring-level given/when/then and `@pytest.mark.parametrize` delivers the
same human-readable specification at zero new-dependency cost and zero maintenance-tax.

Hypothesis was the operator's paired candidate. Its verdict is scoped to HYPOTHESIS-FAILOVER-EVAL
(referenced, not duplicated). The BDD rejection renders the pairing moot regardless.

---

## Work-Multiplier Answer — Who Maintains the Gherkin?

### If the agent maintains gherkin:

The agent must correctly perform a **bidirectional artifact sync**: change the Python step-definition
AND update the corresponding `.feature` file text to match. This is a new failure mode:

1. Agent changes step-definition code → forgets to update `.feature` → **gherkin drift** (step text
   no longer matches behaviour). The test still PASSES (steps run from code, not gherkin), so the
   `.feature` file becomes misleading documentation — worse than no documentation.
2. Agent changes `.feature` text → changes existing step parameter but not a different test's step
   that shared the same text → **step collision** (the same gherkin text now maps to a different
   underlying meaning for different tests).
3. Agent adds a new `.feature` file → references existing step text → finds it at runtime through
   `conftest` discovery → test passes, but no static analysis tool verifies that the step text in
   the `.feature` matches ANY known step definition. The failure is at `pytest` COLLECTION time,
   not at `ruff` lint time.

Our rig already validates agent output via the `accept:` gate (`acceptance.py:49-61`), which runs
`pytest -q` and checks exit 0. An agent that produces gherkin drift will pass this gate (the
drifted test still runs and passes against the code) — the drift is INVISIBLE to the gate.

### If a human maintains gherkin:

Quantified cost: For every behaviour change that touches a BDD-covered feature, the human reviewer
must either:
- Write/review both the Python step-definition AND the `.feature` file (2 artifacts × 1 reviewer)
- OR review an agent's gherkin output for correctness (a new verification class — "did the agent
  write gherkin that actually describes the code it wrote?")

A plain pytest test is ONE artifact. A BDD test is TWO artifacts. That is at minimum a 2×
maintenance-cost multiplier for the human reviewer, and the claimed benefit (better legibility)
does not materialise (see reporting comparison below).

**Cost per behaviour change:** 2 artifacts (`.feature` + `test_*.py`) vs 1 artifact (plain
`test_*.py`). For a behaviour change that touches N existing scenarios, N gherkin scenarios must
be reviewed for drift in addition to the N Python checks.

---

## Per-Feature Evaluation (pytest-bdd 8.1.0)

All tests executed against a real scratch venv at `/tmp/bdd-eval/` with `pytest-bdd==8.1.0`,
`pytest==9.1.1`, `pytest-xdist==3.8.0`. Code at `/tmp/bdd-eval/pytest-bdd/`. Full output archived.

| Feature | Verdict | Evidence |
|---|---|---|
| **Scenario Outlines + Examples tables** | PASS — subsumes `@pytest.mark.parametrize` with tabular syntax | 4-parameter test `Claim by tier` expanded to 4 pytest test cases. Gherkin `Examples:` table maps 1:1 to parametrised test IDs. EXECUTED: all 4 pass (`test_claim.py::test_claim_by_tier[...]`). However, gherkin-to-Python type coercion is MANUAL: the string `"None"` in the gherkin table does NOT auto-coerce to Python `None`; the step definition must handle this explicitly (see `conftest.py:26` — `expected_val = None if expected == "None" else expected`). Every typed value crossing the gherkin→Python boundary needs a coercion wrapper. |
| **Step definition REUSE across features** | PASS — works via `conftest.py` shared imports | Steps defined in `conftest.py` are discoverable by ALL test files in the directory tree. EXECUTED: `test_reuse.py` (references `land.feature`) uses `when the agent runs the land gate` defined in `steps_shared.py`, imported into `conftest.py`. Both scenarios (3/pass, 0/fail) pass. |
| **Step-collision failure mode at scale** | REAL — runtime-only failure, not lint-time | Steps are matched by **text**, not by symbolic reference. If two step definitions in different conftest scopes match the same gherkin text but mean different things, the first-discovered wins — no warning, no error. More dangerously, if a `.feature` file references a step whose definition lives in a SIBLING test file (not in conftest), the step is NOT found at collection time — `StepDefinitionNotFoundError` at RUNTIME. This was confirmed: `test_tags.py` (tags.feature) failed until the claim steps were moved into `conftest.py`. At scale (50+ feature files), step-text conflicts become a naming-discipline burden. |
| **Interaction with pytest fixtures** | PASS — composes cleanly | EXECUTED: `test_fixtures.py` uses a `session`-scoped `db_connection` fixture alongside gherkin `given` steps. The `given` step function receives the fixture as a parameter, and the return value (via `target_fixture`) is passed to downstream `when`/`then` steps. Fixture scope, ordering, and teardown all work. `given` steps can REPLACE setup fixtures entirely (they ARE fixtures), but they can also COMPOSE with existing fixtures — both modes work. |
| **Tags/markers — tier/work_class/money-path** | PARTIAL — works but noisy | Gherkin `@money_path @smoke` tags become pytest marks automatically. EXECUTED: `test_tags.py` with `tags.feature` generates test functions with `@pytest.mark.money_path`, `@pytest.mark.smoke`, etc. Filtering works: `pytest -m money_path` selects only tagged scenarios. LIMITATION: every tag MUST be registered in `pytest.ini` `markers` list to suppress `PytestUnknownMarkWarning`. Our tier names contain colons (`tier:economy`, `work_class:bugfix`) which are valid gherkin tags but NOT valid Python identifiers — pytest-bdd mangled them (the colon was dropped), resulting in `tier:economy` → `@pytest.mark['tier:economy']`? Actually, the warning was `Unknown pytest.mark.tier:economy` — so the colon persists. This means tags with colons cannot be used in `-m` expressions cleanly. CHARON'S EXISTING tier naming (`frontier`, `economy`, `strong`, `sonnet`) would need colon-free aliases for pytest-bdd tag use. |
| **pytest-xdist parallelism** | PASS — survives it | EXECUTED: `pytest -n 2` with all 11 BDD tests across 6 test files. All pass, zero ordering/serialisation issues. pytest-bdd's step-fixture model (function returns become fixture values) is compatible with xdist's subprocess execution model because each worker runs the full conftest → step-definition → test collection chain independently. |
| **Reporting — failure legibility** | FAIL — IDENTICAL to plain pytest assertions | EXECUTED: deliberate assertion failure `claim_result == "tk2 (tier:economy)"` when actual is `tk1 (tier:frontier)`. BDD output: `AssertionError: assert 'tk1 (tier:frontier)' == 'tk2 (tier:economy)'` with `- tk2 (tier:economy)` / `+ tk1 (tier:frontier)` diff. Plain pytest output: IDENTICAL format, same line number, same diff. THE CLAIMED BENEFIT DOES NOT MATERIALISE: a BDD test failure looks exactly like a plain pytest test failure. The `.feature` file's gherkin is NOT shown in the failure output — only the Python step-definition's assertion is shown. The human legibility of BDD comes from READING the `.feature` file (executable specification), not from failure diagnostics. |
| **Maintenance cost — gherkin drift** | REAL — and invisible to the accept gate | EXECUTED: Changed the step-definition `verify_claim` to use a different assertion but left the `.feature` file unchanged. The test PASSES (both code and feature file agree at the gherkin→step-definition boundary), but the gherkin text is now misleading. This class of drift is INVISIBLE to `pytest -q` (the accept gate's mechanism) because the step-definition still matches the gherkin text — only the BEHAVIOUR changed, silently diverging from the specification. To detect this, you would need a second gate that diff-parses `.feature` files and asserts they match the step-definition semantics — writing that gate is hand-rolling a reverse parser, which is precisely the work BDD claims to eliminate. |
| **Failure modes at scale — undefined/ambiguous steps** | CONFIRMED — runtime class, not lint-time | EXECUTED: `test_tags.py` demonstrated `StepDefinitionNotFoundError` when step definitions lived in `test_claim.py` (sibling file, not conftest). `test_ambiguous.py` demonstrated ambiguous steps: `steps_shared.py` defines `a repository with {num_files} changed files` AND `test_ambiguous.py` defines `a repository with {num_files} files` — same parser pattern but one says "changed files" and one says "files". Pytest-bdd does NOT warn about the near-collision; the first-matched step-definition wins silently. At 50+ features, this becomes a naming-tax: every step text must be globally unique or risk silent mis-wiring. |

---

## accept:-Gate Integration Answer

**Confirmed.** The `accept:` commands in a Charon ticket are executed by `AcceptanceCheck.verify()`
at `/home/stack/code/charon/src/charon/acceptance.py:49-61`. The method runs:

```python
proc = subprocess.run(self.cmd, shell=True, cwd=cwd, timeout=600, capture_output=True)
return proc.returncode == 0
```

The check is `exit code == 0`. The command is any shell command — `pytest -q` is already the
documented standard shape. Call sites:
- Coordinator loop: `coordinator.py:170-174` — calls `ledger.verified()` after each agent dispatch
- Land gate: `land.py:338-345` — calls `chk.verify(repo)` in a loop before PR
- End-product validator: `validate.py:70-71` — calls `derive_verified()` and `derive_remaining()`

Because BDD tests run INSIDE pytest (pytest-bdd is a pytest plugin), the accept-gate integration
is **free**: `accept: PYTHONPATH=src python3 -m pytest -q` already covers BDD tests. The same is
true for plain pytest — no integration advantage for BDD. Behave would require a SEPARATE accept
command (e.g., `accept: behave features/`), doubling the gate config surface.

---

## Null-Hypothesis Comparison — Plain Pytest with Disciplined Naming

### What plain pytest gives us for free:

```python
def test_claim_by_tier_economy_eligible():
    """Given a board with economy-eligible tickets,
    when a worker with tier economy claims a ticket,
    then the first economy ticket is claimed."""
    board = ["tk1 (tier:economy)", "tk2 (tier:strong)"]
    eligible = [t for t in board if "tier:economy" in t]
    result = eligible[0] if eligible else None
    assert result == "tk1 (tier:economy)"


@pytest.mark.parametrize("boards,expected", [
    (["tk1 (tier:economy)", "tk2 (tier:strong)"], "tk1 (tier:economy)"),
    (["tk2 (tier:strong)", "tk3 (tier:economy)"], "tk3 (tier:economy)"),
    (["tk1 (tier:strong)", "tk2 (tier:strong)"], None),
    (["tk1 (tier:economy)", "tk2 (tier:economy)"], "tk1 (tier:economy)"),
])
def test_claim_parametrised(boards, expected):
    """Given <boards>, when economy worker claims, then <expected>."""
    eligible = [t for t in boards if "tier:economy" in t]
    result = eligible[0] if eligible else None
    assert result == expected
```

EXECUTED: 8 tests pass. Full code at `/tmp/bdd-eval/null-hypothesis/test_claim.py`.

| Dimension | Plain pytest | pytest-bdd | Delta |
|---|---|---|---|
| Artifacts per test | 1 (`.py` file) | 2 (`.py` + `.feature`) | 2× maintenance cost |
| Parametrisation | `@pytest.mark.parametrize` | Gherkin `Examples:` table | Equivalent; gherkin more readable for many params |
| Human-readable spec | In docstring | In `.feature` file | Gherkin wins for non-programmer stakeholders, but Charon has one operator |
| Step reuse | Functions/fixtures | Step definitions in conftest | Equivalent |
| Type coercion | Native Python | Manual string→type in step | Native Python wins |
| Lint-time correctness | ruff + mypy already run | Step-text match is NOT lintable | Plain pytest wins |
| Gate integration | `pytest -q` (zero change) | `pytest -q` (zero change) | Tie |
| Failure legibility | Assertion + diff | Assertion + diff (IDENTICAL) | Tie |
| Agent bidirectional sync cost | 0 (one artifact) | N × 2 (every behaviour change touches `.feature` + `.py`) | Plain pytest wins |
| New dependency | 0 | `pytest-bdd` (one pip dep) | Plain pytest wins |

### Precisely what BDD adds beyond plain pytest:

1. **A separate `.feature` file** in Gherkin syntax that non-programmers can read. This is the
   CORE value proposition. In Charon's solo-operator context, the operator writes the test
   specification in Python regardless — there is no second stakeholder to read the Gherkin.

2. **Scenario Outline `Examples:` tables** — a more visually tabular parametrisation syntax.
   `@pytest.mark.parametrize` achieves the same result in Python, with native type support.

3. **Step-text-based reuse** — "Given a board with tickets: X" is automatically reusable across
   all features. Plain pytest achieves the same through function calls and fixtures, with the
   added benefit of IDE autocompletion, type checking, and static analysis.

4. **Tags on scenarios** — `@smoke @money_path` directly on the feature text. In plain pytest,
   `@pytest.mark.smoke` on the test function. Equivalent.

**What BDD does NOT add:** better failure reporting, fewer artifacts to maintain, type safety, or
lint-time correctness guarantees. The null hypothesis delivers equivalent legibility at half the
maintenance cost.

---

## Candidates Evaluated

### 1. pytest-bdd — VERDICT: DO NOT ADOPT

Primary candidate. Lives inside pytest, so `accept:` integration is free. Adds one dependency
(`pytest-bdd`). The core cost is the `.feature` gherkin artifact — a second source of truth that
must be kept in sync with code. In an agent-driven rig, this is a work multiplier. See per-feature
table above.

### 2. behave — VERDICT: REJECT

Standalone BDD runner (`behave features/`). EXECUTED: 4 scenarios, 16 steps passed. Adds a
SECOND test runner alongside pytest. The `accept:` gate would need both `pytest -q` AND
`behave features/` as separate commands. Behave uses `context.*` attribute-passing (mutable
global per scenario) rather than pytest's fixture injection — incompatible with the existing
pytest fixture pyramid and xdist parallelism. No integration win over pytest-bdd for a
pytest-native project. Incurring a second-runner cost for zero advantage is wrong.

### 3. Plain pytest with given/when/then naming — VERDICT: ADOPT (null hypothesis wins)

Zero new dependency. Zero gherkin to maintain. One artifact per test. Equivalent legibility
(docstring as specification). Equivalent failure reporting. Full integration with existing
pytest fixture pyramid, xdist, ruff, mypy. This is the baseline that any BDD framework must
beat — and neither pytest-bdd nor behave do.

### 4. Cucumber via Python bridge — VERDICT: REJECT

JVM/JRuby dependency for a Python project. Cucumber's value proposition (non-technical-
stakeholder Gherkin authorship) does not apply to Charon's solo-operator rig. Zero gap it
fills that pytest-bdd + behave do not already cover. Rejected on architecture fit.

### 5. Hypothesis (property-based testing partner) — REFERENCED

Evaluated independently by HYPOTHESIS-FAILOVER-EVAL. Referenced here because the operator
proposed pytest-bdd + Hypothesis as a paired framework. The BDD REJECT verdict renders the
pairing moot regardless of Hypothesis's own outcome, but Hypothesis's standalone value as a
property-based testing tool survives independently of the BDD decision.

---

## The Dependency Collision — Keystone stdlib-only

**Measured 2026-08-02:** The keystone repo at `/home/stack/code/keystone` declares itself
"stdlib-only enforcement layer" (`ksf/__init__.py:1`, `pyproject.toml:8`) with zero runtime
dependencies. Its `dependencies=[]` posture is STRUCTURAL (empty `pyproject.toml`) but NOT
enforced by an automated gate — there is no `tools/check_arch.py`, no `tools/check_boundary.py`,
and no import-policing ksf gate that checks third-party imports.

**The stranded branch does not exist:** The ticket's note mentions `chore/remove-stdlib-only-prohibition`
@ commit `ca7d046` ("adopt-first", 14 files, -215/+85, PUSHED WITH NO PR). This branch and commit
are NOT present in the keystone checkout. No remote or local branch by that name exists. The commit
hash `ca7d046` does not resolve in any keystone branch.

**Whether the BDD verdict depends on this branch:** For CHARON (the product repo), the ADOPT-FIRST
directive in `pyproject.toml:16-21` already permits runtime dependencies — adding `pytest-bdd` to
charon's dev extras would not conflict with any gate. For KEYSTONE (the enforcement layer), the
stdlib-only posture remains. If the BDD verdict had been ADOPT, and if pytest-bdd or Hypothesis
were to be added to keystone (e.g., for property-based test generation), that would REQUIRE the
`chore/remove-stdlib-only-prohibition` branch to land FIRST as a hard prerequisite. Since the BDD
verdict is DO NOT ADOPT, this collision is moot for BDD specifically, but it remains load-bearing
for Hypothesis (see HYPOTHESIS-FAILOVER-EVAL).

---

## If ADOPT — Migration Shape

**N/A — DO NOT ADOPT.** No migration plan is needed. The existing 2380+ plain pytest tests remain
exactly as they are. New tests follow the given/when/then docstring convention already demonstrated.

---

## Evidence Archive

- Executed pytest-bdd test suite: `/tmp/bdd-eval/pytest-bdd/` (11 tests across 6 feature files, all passing)
- Executed behave test suite: `/tmp/bdd-eval/behave/features/` (4 scenarios, 16 steps passing)
- Executed null-hypothesis suite: `/tmp/bdd-eval/null-hypothesis/` (8 tests, all passing)
- Full pytest-bdd run with xdist (2 workers): all 11 tests pass
- Deliberate failure reports compared: BDD vs plain pytest output verified identical

---

## EVAL-REGISTRY Rows

Appended in a separate earlier commit (e99d967) per the substrate-gate requirement. Four rows:
pytest-bdd (DO NOT ADOPT), behave (REJECT — second-runner cost), Cucumber (REJECT — heavy dep),
Hypothesis (REFERENCED — HYPOTHESIS-FAILOVER-EVAL).
