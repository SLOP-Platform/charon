# SETUP-UX-A — first-run setup-UX (3 fixes in `_cmd_setup`)

Dogfood-driven (<self-hosted-dev> 2026-06-27): `charon setup` added provider `opencode-zen`,
stored the key, imported **49** models into the catalog — but the "model served by
'<provider>'" prompt showed nothing, the user hit a blank Enter, and the wizard finished
"Done. 0 model(s) configured" → a silently non-serving gateway. Three fixes, all inside
`_cmd_setup` (`src/charon/cli.py`), shipped as one PR (one function = one ticket).

## Root cause (the real bug, not a count cosmetic)
`_import_models` writes imports into the CATALOG (`models.json`) via `add_models_bulk`,
but the wizard's local `added_models` (used for the final count AND the optional failover
pool) is only appended to inside the manual "model served by" loop. Importing 49 models
left `added_models == 0`: the import→serve step was DISCONNECTED. Fix reconnects it; does
not paper over the count.

## D1 — surface the catalog at the serve prompt (TIER-RECS Phase A)
Before the manual serve loop, `catalog_for(name)` lists the provider's already-imported
ids from `config.load_models()` (offline, required source of truth — no mandatory network
call). Shows up to 20 ids with a `(free)` hint, then offers a one-shot **"serve all N"**
that appends every catalog id to `added_models` and `continue`s past the manual loop (no
per-model re-prompt). No catalog → today's manual prompt is unchanged (no regression).

## D2 — 0-models-served warn guard (correctness)
- End-of-wizard in-place fix: if `added_models` is empty but the configured providers have
  catalog models, offer "serve all N now?" and accept into `added_models`.
- If the served set is STILL empty, WARN loudly on **stderr**
  (`⚠ 0 models served — your gateway won't respond to requests`) with a remediation hint
  (`charon models import <provider>` / re-run `charon setup`) instead of the cheery line.
- N≥1 success path kept **byte-identical** (`Done. N model(s) configured…`). Exit stays 0 —
  the user walked the wizard to completion; the warning is the signal, not a non-zero code.

## D3 — colorize the presets line (UX-POLISH)
Module-level `_ansi_emph` (stdlib-only, `os`/`sys`) bold-cyans the `Presets:` line. Plain
fallback on `NO_COLOR` set to ANY value (incl. empty → `is not None`), `TERM=dumb`, or a
non-TTY stdout. Unit-tested directly (forced-TTY vs each fallback).

## Scope / constraints
- Owned files only: `src/charon/cli.py`, `tests/test_setup_ux.py`. `config.py` /
  `providers.py` untouched (read-only) — `load_models()` already exposes the catalog.
- Provider/agent-agnostic (no hardcoded provider id); config-step only, never the hot path;
  no new dependency; product-clean (no fleet/SLOP/runner leak).
- Gate green every commit: pytest (559) · ruff · mypy · boundary · version.

## Test note
The 8 new tests drive `cli.main(["setup"])` with monkeypatched `input`/`getpass` and an
isolated `$CHARON_HOME` (mirrors `tests/test_config.py`). Because monkeypatched `input`
discards the prompt string, prompt-text assertions aren't possible under capsys — the
in-place-fix test instead asserts on the resulting `serving N model(s)` print + final count
(and that the catalog block's distinct "… from '<provider>'" print did NOT fire), which
uniquely pins the end-guard path.
