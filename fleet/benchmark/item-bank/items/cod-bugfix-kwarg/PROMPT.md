# Task: add a back-compat `force_refresh` kwarg to `apply_to_env`

`secrets.py`'s `apply_to_env()` currently uses `os.environ.setdefault(k, v)`,
which is a structural no-op for any key already resident in the process
environment. That defeats hot-rotation: rotating a key on disk doesn't
take effect for an already-running process.

Add a `force_refresh` keyword-only parameter to `apply_to_env()`:

```python
def apply_to_env(*, force_refresh: bool = False) -> None:
    ...
```

- Default (`force_refresh=False`): UNCHANGED behavior — `setdefault`
  semantics (an already-resident env var always wins).
- `force_refresh=True`: OVERWRITE an already-resident key with the
  current on-disk value (use `os.environ[k] = v`).

Hard constraints:
1. Do not weaken any existing guard. The `_KEY_ENV_RE` well-formed-name
   check and the `_SENSITIVE_ENV` skip-list (`LD_PRELOAD`, `PATH`,
   `PYTHONPATH`, ...) MUST apply in BOTH modes, identically.
2. Touch only `secrets.py` (and `tests/test_secrets.py` for the new
   test). Do NOT change the call site in `cli.py`.
3. No secret is ever printed or logged.
