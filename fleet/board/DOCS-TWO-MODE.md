tier: sonnet
work_class: docs
branch: feat/docs-two-mode
depends_on:
owns: README.md, docs/getting-started.md
prompt: /home/stack/charon-private/prompts/docs-two-mode.md
note: ACTIVE / claimable. Implement the operator-approved two-mode onboarding (gateway vs
  orchestrator) — see the draft `dogfood/TWO-MODE-ONBOARDING-DRAFT.md`. PRODUCTION-READINESS
  onboarding priority: replace the jargon-heavy README intro with the approved "Charon in 20
  seconds" block + "Which mode do I want?" table + Mode A / Mode B quickstarts; keep the deep
  Mode-B internals down in the existing "Work engine (opt-in)" section. Add a new
  `docs/getting-started.md` carrying the same content (slightly expanded) + a one-line README
  pointer to it. Canonical tier: sonnet (docs). Reproduce the approved copy/commands faithfully
  — every command was verified against origin/master `src/charon/cli.py`.
  PROVISIONAL: `docs/getting-started.md` filename is the droid's call (may use
  `docs/quickstart.md` if it fits the repo better) — pick one, use it consistently in the file,
  the README pointer, and the PR.
  OWNS-COLLISION CHECK (authoring, 2026-06-27): `README.md` is also owned by E7, FR1, and
  DOCKER-INSTALL — ALL DONE (state/done/) — so the validator reports an all-done/historical
  hand-off (INFO), NOT a live collision. RELEASE-SMOKE-FIX (submitted/live) owns only
  `.github/workflows/release.yml`, not README.md. `docs/getting-started.md` is a NEW path owned
  by no other ticket. So DOCS-TWO-MODE is the only LIVE owner of README.md. Validate = GREEN.
  CONSTRAINTS: product-clean (no SLOP/fleet/rig leak), agent/provider-agnostic, jargon-free
  landing content, don't break existing README anchors/links, keep it tight + skimmable, keep
  every command accurate to the real CLI. Draft branch from master, DRAFT PR, never merge.
