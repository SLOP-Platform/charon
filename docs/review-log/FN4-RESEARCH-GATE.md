# FN4-RESEARCH-GATE — Research discipline protocol

## Decision

Build `fleet/research.sh` as a mechanized research/review/comparison protocol that
composes existing primitives (reuse-check.sh, KS29 registry pattern, FN2 bi-temporal
decay) into a single launcher with a pre-launch dedup/staleness gate, enforced
methodology injection, and a post-output completeness verifier.

## Key design choices

- **Registry = flat `.md` files** under `fleet/state/research-registry/`, matching
  KS29's pattern. No extra DB; frontmatter (`topic`, `recorded_at`, `verdict`) is
  the schema.
- **Freshness = FN2 bi-temporal decay** (`exp2(-age/half-life)`): fresh threshold
  at weight > 0.5. Configurable via `RESEARCH_FRESHNESS_DAYS` (default 30).
- **Verifier runs in Python** (embedded heredoc) for regex readability; 5 checks,
  numbered and deterministic for FAIL-ON-REVERT stability.
- **Pre-launch exit codes**: 0 = FRESH cached record (no sub-session needed);
  10 = sub-session launch signal (STALE/MISSING). Callers check rc to branch.
- **Adversarial second pass** gated behind `RESEARCH_REQUIRE_2ND_PASS=1`; writes
  a `.admit-by-$(whoami).$(date)` token into the registry dir. Two independent
  operators must admit the same record.

## Tests (33 pass)

| Group | Tests | What it proves |
|---|---|---|
| Verifier gate (A) | a1–a6 | Rejects uncited prose, missing reuse-check, no cards, no verdict; PASS on valid; DISABLE toggle bypasses (intentionally) |
| Pre-launch gate (B) | b1–b4 | FRESH→cache hit (exit 0), STALE→UPDATE prompt (exit 10), MISSING→full prompt (exit 10), `--force` bypass |
| Registry list (C) | c1–c3 | `--list` renders both fresh and stale slugs |
| Min-sources (D) | d1–d3 | `RESEARCH_MIN_SOURCES` enforces/waives source count |

## Scope

Only `fleet/research.sh` (owns). No files outside owns were created or edited.
