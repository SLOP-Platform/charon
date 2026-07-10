# TEST-HARDEN-CONTRACT — review log

Resubmit after PR #87 REJECTED 2026-07-10 (`scratch/review-pr87-testharden.md`). Two
defects; both addressed below.

## Defect 1 — `anthropic` self-mirroring false-green (FIXED)

`anthropic` is `wire=WIRE_ANTHROPIC` (native `/v1/messages`; no top-level `choices`;
response translation is Phase-2 per `providers.py`'s own note). The prior version fed it
the fabricated OpenAI-shaped `_canonical_shape` mock, so it passed green for the wrong
reason — the exact blind spot this ticket exists to kill.

Fix (`tests/test_provider_response_contract.py`):
- Added `_anthropic_native_shape` — a real Anthropic Messages-API shape (`type:
  "message"`, `content: [...]` blocks, `usage.input_tokens`/`output_tokens`; no top-level
  `choices`).
- `anthropic` removed from `_OPENAI_SHAPE_PRESETS`; native-wire fixture lookup is now
  derived from `providers.PRESETS[name].wire` (`_NATIVE_WIRE_SHAPE_FIXTURES`), not a
  hand-picked name, so a future `WIRE_ANTHROPIC` preset is covered automatically instead
  of silently joining the OpenAI-shape set.
- The `anthropic` parametrization case is now `xfail(strict=False)`, same mechanism and
  same reasoning as `cline-pass` (relayed verbatim today, no top-level `choices`).
- `test_every_preset_has_a_declared_shape_fixture` updated to also accept native-wire
  presets as "declared" (still fails loudly on anything truly undeclared).
- Fixed the `_canonical_shape` docstring's false universal claim.

Verified: `anthropic` and `cline-pass` are the only two xfails; all 25 other presets pass
on the real assertion (top-level `choices` + `usage`).

## Defect 2 — self-mirroring lint gates nothing (PARTIALLY ADDRESSED — scope-blocked)

The review asked to wire the rule (e) enforcer into `python3 -m charon.cli gate` as an
ERROR, proven by a planted mock failing the gate and a clean codebase passing.

**What's in scope and done:** `tools/check_test_patterns.py`'s docstring now states
plainly that rule (e) gates under `--strict`, and `tests/test_check_test_patterns.py`
adds `test_strict_mode_fails_on_self_mirroring_mock` /
`test_strict_mode_passes_clean_fixture` — isolated `tmp_path` proof that `--strict`
actually exits nonzero on a planted self-mirroring mock and exits 0 on a clean fixture.

**What's blocked, and why:** two things prevent going further, both outside this
ticket's `owns:`:

1. Wiring the tool into `python3 -m charon.cli gate` means adding an entry to
   `CHECKS` in `src/charon/gate_runner.py` — not in this ticket's `owns:`
   (`tests/conftest.py`, `tests/test_provider_response_contract.py`,
   `tools/check_test_patterns.py`, `tests/test_check_test_patterns.py`). Per the robot-mode
   ownership rule, a file outside `owns:` may not be edited even when the fix logically
   wants it — `tools/gates.json` (the sibling registry, already listing `test-patterns` as
   `ci_step: true`) is explicitly owned by DTC-1 and CI-WORKFLOW-POLICY-GATE, confirming
   this cluster of files is actively contested/owned elsewhere, not just incidentally
   untouched.
2. Independent of (1): promoting rule (e) from WARNING to an unconditional ERROR would
   immediately break the tool against the *live* `tests/` tree. Confirmed by running
   `PYTHONPATH=src python3 tools/check_test_patterns.py tests`: four files this ticket
   does not own already contain the self-mirroring pattern —
   `tests/test_agent_launch_routing.py`, `tests/test_fallback_provider.py`,
   `tests/test_gateway.py`, `tests/test_proxy_server.py`. Also confirmed
   `--strict` against the live tree today exits 1 with **1019** pre-existing
   docstring/parametrize-ratio warnings across the repo, unrelated to rule (e) or this
   ticket — the whole tree is not `--strict`-clean yet, so gating on `--strict`
   wholesale is a separate, larger cleanup.

**Recommended follow-up** (new ticket, not this one): add
`(["python3", "tools/check_test_patterns.py", "tests", "--strict"], "test-patterns")` (or
a rule-(e)-only flag) to `gate_runner.py`'s `CHECKS`, bundled with fixing the top-level
contract assertion in the 4 files above so the gate doesn't go red on unrelated
pre-existing debt the moment it's wired in.
