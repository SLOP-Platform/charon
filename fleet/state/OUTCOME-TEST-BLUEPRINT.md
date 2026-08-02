# OUTCOME-TEST-BLUEPRINT — `test_gateway_outcome.py`

**Status:** proposal reviewed adversarially, 2026-08-02. Operator-supplied blueprint preserved
verbatim in §1; review in §2; corrected implementation in §3.

**Verdict: THE THESIS IS RIGHT. THE IMPLEMENTATION AS WRITTEN WOULD PASS ON A GATEWAY THAT HAS
NO FAILOVER AT ALL** — it carries both of the two defect shapes that caused 6 of 8 PR bounces on
2026-08-02 (`fleet/board/PR-QUEUE-DRIVE.md`). Do not land §1. Land §3, or something like it.

---

## 1. THE PROPOSAL AS SUPPLIED (verbatim — do not edit; this is the provenance)

```python
import json
import os
import pytest

# ==============================================================================
# AGENT HANDOVER MANIFEST (DO NOT DELETE)
# ==============================================================================
# CURRENT GOAL: Assert that when Upstream Provider A fails, Gateway falls back to Provider B.
# LAST COMPLETED: Verified mock endpoint shapes.
# NEXT STEP FOR NEXT AGENT: Run `pytest test_gateway_outcome.py`. If it fails, fix the
# failover routing logic in the gateway code until this test passes. Do not touch this test.
# ==============================================================================

def test_gateway_failover_outcome():
    """
    OUTCOME ASSERTION:
    We do not care HOW the gateway routes the traffic internally.
    We only care that a file named 'final_ledger.json' is created,
    and it contains a successful 200 status code.
    """
    artifact_path = "final_ledger.json"
    if os.path.exists(artifact_path):
        os.remove(artifact_path)

    os.system("python run_gateway_pipeline.py")

    assert os.path.exists(artifact_path), "FAIL: The pipeline did not output a final_ledger.json file!"

    with open(artifact_path, "r") as f:
        ledger_data = json.load(f)

    assert ledger_data.get("status") == 200, f"FAIL: Expected status 200, but got {ledger_data.get('status')}"
    assert "response_payload" in ledger_data, "FAIL: Ledger is missing the final response data."
```

---

## 2. ADVERSARIAL REVIEW

### 2.0 What is RIGHT and must be preserved
- **Outcome over mechanism.** Asserting on the artifact rather than the call sequence is correct
  and matches the design principle that the ledger is the vendor-neutral source of truth.
  MEASURED 2026-08-02: `src/charon/ledger.py` EXISTS, so the assertion surface is real, not
  aspirational.
- **The AGENT HANDOVER MANIFEST is a genuinely good idea** and directly addresses the operator's
  standing complaint that work gets dropped between sessions. It is the only part of this file
  that is novel. It must become MECHANICAL to be worth anything (see D5).

### 2.1 D1 — FATAL: THIS TEST DOES NOT TEST FAILOVER
The docstring and manifest both claim it asserts "when Provider A fails, Gateway falls back to
Provider B". **Nothing in the test makes Provider A fail.** There is no fault injection, no
provider stub, no error-code forcing. The test exercises the HAPPY PATH and asserts it succeeded.

Consequence: it is **green before the failover code exists, green after, and green with failover
entirely reverted.** By `PR-QUEUE-DRIVE`'s own bar — *"RUN THE SUITE WITH THE CHANGE REVERTED;
if it still passes, the suite does not cover the change"* — this is defect shape #2, the single
most common bounce reason in this repo. A suite that cannot fail is worse than no suite, because
it reads as proof.

**This alone disqualifies §1 from landing.**

### 2.2 D2 — FATAL: `os.system()` DISCARDS THE EXIT CODE, SO INFRA FAULTS MASQUERADE AS BEHAVIOUR FAILURES
`os.system(...)` returns a status that is never checked. VERIFIED 2026-08-02:
**`run_gateway_pipeline.py` does not exist in the product repo.** So today this test would:
1. run `python run_gateway_pipeline.py` → shell prints "No such file or directory", rc 127,
2. discard that,
3. fail at the artifact assert with **"FAIL: The pipeline did not output a final_ledger.json
   file!"**

The reported cause is wrong. The real cause is "the runner does not exist". This is precisely the
misclassification class fixed in `fleet/charon-run.sh` earlier today, where provider faults were
being charged to the model. **"Could not run" and "ran and produced the wrong answer" must never
produce the same failure message.**

### 2.3 D3 — THE ASSERTED PROPERTY IS FALSE FOR THIS SYSTEM
`assert status == 200` encodes "failover always eventually succeeds". MEASURED 2026-08-02 across
380 agent logs: **47 sessions legitimately terminated `CHARON_RUN_RESULT=EXHAUSTED`** — every leg
in the chain failed for real reasons (Groq TPM ceiling 8000 vs 44,225 requested; DeepSeek region
opt-in). Chain exhaustion is a CORRECT terminal state, not a bug.

A correct gateway with a fully-capped pool FAILS this test. The property must be:

> the pipeline terminates with EITHER a 200 and a well-formed payload, OR a well-formed
> exhaustion result naming the legs it tried — and NEVER hangs, NEVER writes a partial ledger,
> and NEVER reports success without a payload.

### 2.4 D4 — CWD-RELATIVE ARTIFACT PATH
`"final_ledger.json"` resolves against pytest's invocation directory, not the test file. It
therefore (a) writes into the repo root, (b) collides with itself under `pytest-xdist` parallelism,
(c) behaves differently depending on where the runner was launched — and the `accept:` execution
guard runs commands from a worktree root that is not fixed. Use the `tmp_path` fixture.

### 2.5 D5 — "Do not touch this test" IS PROSE, NOT ENFORCEMENT
This is defect shape **#1** from `PR-QUEUE-DRIVE`: *a safety property asserted in prose that the
code does not implement.* An agent optimising for a green gate can edit or delete the test, and
nothing stops it. The instruction is aimed at exactly the actor most likely to ignore it.

To be real it needs a mechanical guard — a checked-in hash of the test file verified by CI, a
CODEOWNERS-style protected path, or a gate that fails when the assertion count in the file drops.
Until then the manifest is a comment, and comments do not gate.

### 2.6 D6 — NOT HERMETIC (money-path)
Shelling to the real pipeline means real upstream calls: real spend, real latency, real flake, in
a test. The money path must not be exercised by a merge gate. Stub the upstreams.

### 2.7 D7 — MINOR BUT REAL
- `python` should be `sys.executable` — under a venv `python` may be a different interpreter.
- **No timeout.** A hung pipeline hangs CI forever. Latency is a failure class here.
- `"response_payload" in ledger_data` proves a key exists, not that it is non-empty or shaped.
- `import pytest` is unused in §1.
- No teardown on failure; the artifact leaks into the next test.

### 2.8 DUPLICATION CHECK — three failover suites already exist
`tests/test_gateway_failover.py` (368 lines), `tests/test_failover.py` (186),
`tests/test_cli_chat_failover.py`. **MEASURED: both of the first two contain ZERO
`assert_called`/`call_args`/`mock_calls`/`side_effect` assertions** — they are already
outcome-shaped, not call-order-mocked. This weakens the common assumption that our failover tests
are order-fragile, and it means a new file must justify itself against what exists rather than
assume a gap. Extend them, or state plainly what they do not cover.

---

## 3. CORRECTED IMPLEMENTATION (the shape that should actually be built)

Illustrative, not yet landed — the ticket that lands it must red-proof it.

```python
"""Outcome-level failover assertion. Asserts WHAT the pipeline produced, not HOW."""
import json
import subprocess
import sys
import pytest

# ==============================================================================
# AGENT HANDOVER MANIFEST  (enforced by fleet/checks/outcome-test-integrity.sh —
# editing this file without updating that gate's recorded hash FAILS CI.)
# ==============================================================================
# GOAL: with the first upstream forced to fail, the pipeline must still reach a
#       well-formed terminal state and record which legs it attempted.
# NEXT AGENT: fix the ROUTING CODE until this passes. Do not weaken this test:
#             its assertion count and file hash are gated.
# ==============================================================================

PIPELINE = "run_gateway_pipeline.py"   # must exist; see test_runner_exists


def test_runner_exists():
    """Separate INFRA failure from BEHAVIOUR failure — never let them share a message."""
    assert (pytest.importorskip("pathlib").Path(PIPELINE)).exists(), (
        f"INFRA (not a behaviour failure): {PIPELINE} is missing. "
        "The pipeline was never invoked, so no conclusion about failover can be drawn."
    )


def test_gateway_failover_outcome(tmp_path, monkeypatch):
    ledger = tmp_path / "final_ledger.json"

    # ARRANGE — force the FIRST upstream to fail, or this asserts nothing about failover.
    monkeypatch.setenv("CHARON_FAULT_INJECT", "provider_a=503")
    monkeypatch.setenv("CHARON_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("CHARON_UPSTREAM_MODE", "stub")   # hermetic: no real spend

    # ACT — capture rc/stdout/stderr and BOUND the runtime.
    proc = subprocess.run(
        [sys.executable, PIPELINE],
        capture_output=True, text=True, timeout=120, cwd=tmp_path,
    )

    # ASSERT INFRA FIRST, with its own distinct message.
    assert proc.returncode != 127, f"INFRA: runner not found. stderr={proc.stderr[:400]}"
    assert ledger.exists(), (
        f"No ledger written. rc={proc.returncode} stderr={proc.stderr[:400]}"
    )

    data = json.loads(ledger.read_text())          # malformed JSON => hard failure, correctly

    # ASSERT THE REAL PROPERTY — success OR honest exhaustion, never a silent lie.
    assert data.get("status") in (200, "EXHAUSTED"), f"unexpected terminal state {data.get('status')!r}"

    attempts = data.get("attempts", [])
    assert len(attempts) >= 2, (
        f"FAILOVER NEVER HAPPENED: provider_a was forced to 503 but only {len(attempts)} "
        f"attempt(s) recorded. This is the assertion that makes the test about failover."
    )
    assert attempts[0].get("provider") == "provider_a"
    assert attempts[0].get("outcome") != "success"

    if data["status"] == 200:
        payload = data.get("response_payload")
        assert payload, "status 200 with empty payload — silent success is the worst outcome"
        assert attempts[-1].get("outcome") == "success"
    else:
        assert data.get("exhaustion_reason"), "EXHAUSTED without a reason is indistinguishable from a crash"
```

### Why §3 satisfies the bar §1 fails
| bar | §1 | §3 |
|---|---|---|
| can it FAIL when failover is reverted? | no — green regardless | yes — `attempts >= 2` goes red |
| infra vs behaviour distinguishable? | no | yes — separate test + rc 127 check |
| property true of this system? | no — ignores legitimate exhaustion | yes — 200 OR EXHAUSTED |
| parallel-safe / path-stable? | no | yes — `tmp_path` |
| hermetic on the money path? | no | yes — stub mode |
| bounded runtime? | no | yes — `timeout=120` |
| manifest enforced? | prose only | hash-gated |

---

## 4. OPEN QUESTIONS FOR THE IMPLEMENTING TICKET
1. Does the ledger currently record a per-attempt list with provider + outcome? If NOT, §3's
   central assertion is unimplementable and **adding those fields is the prerequisite** — that is
   a finding worth more than the test.
2. Does a fault-injection hook (`CHARON_FAULT_INJECT`) exist, or must it be built? A test that
   needs a product change to be writable is a design signal, not an obstacle.
3. Should this extend `tests/test_gateway_failover.py` (368 lines, already outcome-shaped) rather
   than add a fourth failover file?
4. Is the AGENT HANDOVER MANIFEST worth generalising to ALL gate-critical tests? It is the most
   novel idea in the proposal and it addresses the operator's standing drop-work concern.
