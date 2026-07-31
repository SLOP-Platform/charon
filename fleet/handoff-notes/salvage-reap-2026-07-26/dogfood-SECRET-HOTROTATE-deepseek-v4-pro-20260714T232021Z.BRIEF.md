# SECRET-HOTROTATE — secret hot-rotation force-refresh (self-contained)

You are working in an isolated git worktree checked out from `origin/master`. Everything you
need is in this repo. Do NOT register anywhere, do NOT wait on any other ticket — just make the
change below and stop.

## What's broken

`src/charon/secrets.py:90-97`, `apply_to_env()`:

```python
def apply_to_env() -> None:
    for k, v in load_secrets().items():
        if _KEY_ENV_RE.match(k) and k not in _SENSITIVE_ENV:
            os.environ.setdefault(k, v)
```

`os.environ.setdefault(k, v)` is a literal structural no-op for any key already resident in the
process environment. That means: rotate a provider key on disk (e.g. `HF_TOKEN` via the gateway
host's rotate-key helper), and the running gateway process — which already has the OLD value of
that key resident in its env from startup — never picks up the new value. Only a full
container/process restart does. This defeats the point of hot rotation.

## Required change

Add a `force_refresh` keyword-only parameter to `apply_to_env()`:

```python
def apply_to_env(*, force_refresh: bool = False) -> None:
    ...
```

- **Default (`force_refresh=False`)**: UNCHANGED behavior — an explicit/already-resident env var
  always wins (`setdefault` semantics), exactly as today. This is a backward-compatible additive
  change; every existing call site is unaffected.
- **`force_refresh=True`**: OVERWRITES an already-resident key with the current on-disk value
  (i.e. `os.environ[k] = v` instead of `setdefault`), so a rotated key takes effect live.

### Hard constraints

1. **Do not weaken any existing guard.** The `_KEY_ENV_RE` well-formed-name check and the
   `_SENSITIVE_ENV` skip-list (`LD_PRELOAD`, `PATH`, `PYTHONPATH`, …) apply in BOTH modes,
   identically — `force_refresh` only changes whether an already-resident *legitimate* key is
   overwritten, never which keys are eligible to load at all.
2. **No secret is ever printed or logged** — this file's existing invariant (nothing here ever
   prints a key) is unchanged.
3. Touch only: `src/charon/secrets.py`, `tests/test_secrets.py`. Do not touch the CLI
   (`src/charon/cli.py`) or wire `force_refresh` into any caller — this ticket is scoped to the
   `secrets.py` primitive only; a follow-on ticket wires a hot-rotate CLI/endpoint that calls it.

## Acceptance (what will be checked)

1. `apply_to_env(force_refresh=True)` is callable and, given a key already resident in
   `os.environ` under an OLD value plus a NEWER value stored via `set_secret()`, results in
   `os.environ[k]` holding the NEW value after the call.
2. `apply_to_env()` (no args, or `force_refresh=False`) is byte-for-byte unchanged in behavior —
   a resident key still wins (existing test `test_apply_to_env_does_not_override_explicit` must
   keep passing untouched).
3. `pytest tests/test_secrets.py -q` passes (no regression).
4. **`tests/test_secrets.py` contains at least one NEW test function whose name matches
   `test_.*(force_refresh|hot_rotat).*`.** This is checked mechanically (grep-by-name over the
   diff), not just "the suite passes" — the pre-existing suite already passes 10/10 on an
   untouched checkout with ZERO force-refresh coverage, so re-running it alone proves nothing.
   You must add a genuinely new test under that name pattern that: sets an env var to a stale
   value, stores a different (rotated) value via `set_secret()`, calls
   `apply_to_env(force_refresh=True)`, and asserts the env var now holds the rotated value (and,
   ideally, also asserts the non-force-refresh call still leaves the stale value in place).

### DOGFOOD_TEST_CMD (discriminating — new named test added + it passes + no regression)

```
PYTHONPATH=src python3 -m pytest tests/test_secrets.py -q \
  && python3 -c "import re,sys; c=open('tests/test_secrets.py').read(); \
       sys.exit(0 if re.search(r'def test_.*(force_refresh|hot_rotat)', c) else 1)"
```

This fails on unmodified `origin/master` today — the pytest half PASSES (10/10, no regression
to detect), but the grep-confirm half fails (no such test name exists yet), so the compound
command is RED before a fix and only turns GREEN once a real `force_refresh` implementation AND
a matching new test name are both present. Verified via a throwaway `git worktree`, 2026-07-13 —
RED-proof=OK per `fleet/benchmark/test-quality-gate.py`.

## PRODUCT-BOUNDARY note

This BUILD touches Charon PRODUCT code (`src/charon/secrets.py`). Keep the change STANDALONE —
stdlib only, no fleet/rig/SLOP dependency leaking into `src/charon`.
