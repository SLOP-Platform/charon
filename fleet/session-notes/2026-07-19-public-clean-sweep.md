# PUBLIC-CLEAN sweep — STOPPED before Step 2. Premise disproven.

Raw inventory: `2026-07-19-public-clean-sweep-inventory.txt` (237 hits).

## Why stopped
Brief's diagnosis: "gate has a blind spot for rig taxonomy; 16 review-log files leaked past it."
Code says otherwise on the headline case.

1. `/home/stack` + `charon-private` ARE already gate patterns
   (`tools/check_public_clean.py:22-23`). Master is GREEN today.
   Every such hit is **deliberately waived** via `tools/.public-clean-exceptions.json`
   — 26 files / 92 lines.
   The brief's "worst" line, `docs/review-log/TIER-5.md:4`
   `_owns: /home/stack/charon-private/fleet/claim.sh_`, is verbatim in that
   ledger. It did not slip past a blind spot; it was allow-listed.
   => Adding patterns will NOT catch it. Fix = ledger removal, a different change.

2. True blind spot is only the *bare* taxonomy (no path prefix): `fleet/`,
   `droid`, `SLOP`, `claim.sh`, `fleet-droid.sh`, `TIER-N` contracts.
   ~70 files, ~237 hits — 4x the brief's estimate.

## Three blockers that are decisions, not text edits
- **`tools/gates.json:56,186`** — live enforcers point at
  `../charon-private/fleet/validate_board.sh` and `.../checks/no-unreachable-paths.sh`,
  plus a whole `"domain": "fleet"` gate, inside the PRODUCT gate registry.
  `tools/check_gate_registry.py:70` resolves these. Sweeping the text breaks gates.
  This is the product-vs-build-rig boundary violated in product config.
- **`docs/adr/0002-project-boundary-and-slop-integration.md`** — 58 hits; the ADR's
  entire subject is integration with the private SLOP/mediastack project. It is
  load-bearing: `tools/check_boundary.py:3,110` and `tests/test_boundary.py` enforce
  its INV-B1/B5 *by name*. Also carries `**Deciders:** Nnyan (solo operator)` — a
  personal handle the gate's name pattern (only `Rafael`, line 26) does not catch.
- **`src/charon/cli.py:765-772,1820-1828`** — `charon tier ranks` documented as
  "consumed by claim.sh (TIER-5)", `resolve` "for fleet-droid.sh TIER-6 ... cheapest
  **Anthropic**-API-runnable model id for `claude -p`". Product CLI carries a
  machine-parseable contract whose only consumer is the private rig, and it
  hardcodes Anthropic (collides with SG-never-Anthropic).

## Classification
- REAL LEAK, safe to rewrite: docs/review-log/* + docs/PLAN-tier*.md + most ADR
  prose (~55 files) — product-neutral rewrite is mechanical.
- DELIBERATE WAIVER, do not touch: `docs/review-log/PUBLIC-CLEAN-LINT.md:13,14,51,55`
  (confirmed: inline `<!-- public-clean: allow — documentation of pattern -->`),
  `tools/check_public_clean.py:26`, `tests/test_public_clean.py` fixtures,
  `tools/check_boundary.py` / `check_no_rig_import.py` (must name what they block).
- FALSE POSITIVE, must not pattern on: `manager`, `operator`, `board/`,
  `depends_on:`, `parked:` — all legitimate product vocabulary
  (`src/charon/engine/board.py`, drain-then-park lifecycle, ADR operator persona).

## Step 5 note (gathered, unused)
8 open PRs; **6 are DRAFT** (#172 #171 #170 #169 #164 #161) => hard stop each.
Non-draft: #135, #86 (dependabot).
