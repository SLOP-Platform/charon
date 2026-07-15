# Task: rename `cost_rank` to `price_rank` across >=3 files

`config.py` defines `cost_rank`. The convention is being renamed to
`price_rank` across the project.

Rename `cost_rank` -> `price_rank` consistently across the codebase:

- Update the canonical definition in `config.py`.
- Update ALL call sites in `routing.py`, `meter.py`, and `providers.py`
  (4 call sites total).
- Update the docstring reference in `config.py`.

Hard constraints:
- Rename only `cost_rank` (not `cost_class`, not `cost_usd`, not
  `cost_band` — those names are NOT being changed).
- The renames must be exact: no aliases, no compatibility shims.
- The test suite must pass with the new name in effect.
- Do NOT touch the unrelated `providers.json` file in `data/`.
