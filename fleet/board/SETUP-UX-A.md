tier: opus
branch: feat/setup-ux-a
depends_on:
owns: src/charon/cli.py, tests/test_setup_ux.py
prompt: /home/stack/charon-private/prompts/setup-ux-a.md
scope: PRODUCTION-READINESS / first-run setup-UX. Bundles THREE setup-UX fixes that ALL live
  in one function (`_cmd_setup` in `src/charon/cli.py`) — so they are ONE ticket (a droid can't
  split a single file): (1) surface the provider's imported/live catalog at the "model served
  by '<provider>'" prompt + offer "serve all N imported / pick from these" (TIER-RECS Phase A
  core); (2) a 0-models-served WARN guard so the wizard never cheerily finishes "Done. 0
  model(s) configured" on a silently non-functional gateway, and offers to fix it; (3) colorize
  the "Presets: …" line (ANSI with NO_COLOR + non-TTY plain fallback). Dogfood-driven
  (charon-vm 2026-06-27: imported 49 models, served 0, blank serve prompt). Implements
  TIER-RECS Phase A (Findings 1 & 2) + the UX-POLISH colorize-presets nit.
note: ACTIVE / claimable. owns is `cli.py` + its own new test file `tests/test_setup_ux.py`;
  config.py is NOT owned — `config.load_models()` already exposes the imported catalog, so the
  fix is cli.py-only (verified by reading config.py at authoring). No owns-collision: every
  other ticket that owns `src/charon/cli.py` (S1, E6, FR1, INTAKE1, N2, TIER-3) is DONE, so this
  is the only LIVE owner of cli.py. Claimed by the `opus` tab.
