# PUBLIC-CLEAN-LINT — mechanize "no personal/internal info in the public repo" + scrub current leaks

## Dependencies & sequence
**depends_on: NONE.** Owns a new tool + `tools/check_boundary.py` + its test (+ scrubs flagged
files). Disjoint from all parked backlog → safe concurrent. Wave: standalone.

## Why
charon + mediastack are PUBLIC; internal info keeps leaking in and we've scrubbed repeatedly (audit
2026-06-28: `4-lom`/`charon-vm` hostnames, `/home/stack/charon-private` rig paths in ~20 charon
files; mediastack far worse). One-time scrubs don't stick — MECHANIZE the prevention.

## What to build
1. **Lint (the durable fix):** `tools/check_public_clean.py` — hard-fails (non-zero) if tracked
   files contain personal/internal patterns: internal IPs (`10\.0\.`), hostnames (`4-lom`,
   `charon-vm`), home paths (`/home/stack`), the rig name (`charon-private`), and obvious
   token shapes (hex≥32). Allow a small, reviewed `# public-clean: allow <reason>` inline waiver +
   a config of intentional exceptions (e.g. the CI_RUNNER design note, if kept). Wire it into the
   gate (alongside `check_boundary.py`) and CI so it blocks future leaks.
2. **Scrub** the files the lint flags: redact hostnames→generic (`<self-hosted-runner>`), remove
   `/home/stack/...` absolute paths→relative/generic, keep the design intent without the personal
   specifics. Run the lint until clean.
3. **RESEARCH (document in the review-log):** how to mechanize this for BOTH repos durably — a
   pre-commit hook + CI check sharing one pattern list; whether mediastack's `ms-enforce` can host
   the same check; and whether the `.claude/` dev-meta should be gitignored/removed from the public
   tree entirely. Output a concrete cross-repo recommendation (the SLOP-side ticket implements it).

## Acceptance
- `tests/test_public_clean.py`: the lint flags a planted leak (IP/hostname/home-path/token) and
  passes on a clean tree; the waiver mechanism works. `python3 tools/check_public_clean.py` exits 0
  on the scrubbed repo. Existing gate stays green.

## CONSTRAINTS
Own: `tools/check_public_clean.py`, `tools/check_boundary.py`, `tests/test_public_clean.py`, plus the
flagged doc/workflow files it scrubs (finalize the scrub list at activation). Stdlib only; no secrets.
Gate green; conventional commits; review-log → `docs/review-log/PUBLIC-CLEAN-LINT.md`. Draft PR,
`submit.sh`, STOP. BACKLOG (parked). Branch `feat/public-clean-lint`.
