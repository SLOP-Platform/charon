# FIX-PUBLIC-CLEAN-SHA-PINS — review log

## Problem

`tools/check_public_clean.py` flagged every dependabot bump that touched
`uses: org/action@<40-hex-sha>` in `.github/workflows/*.yml` as a
"hex token shape" violation. The exceptions ledger listed each such line
verbatim to silence the gate, so every dependabot PR had to also re-author
`tools/.public-clean-exceptions.json` to add the new SHA — turning a routine
action-version bump into a multi-file change. PR #86 was blocked on this.

## Decision

Add a path- AND shape-scoped allowlist inside `_scan_content`: a line is
exempted from the generic 40-hex pattern **only when** (a) it syntactically
matches `uses: org/action@<40-hex>` (the commit-SHA pin) AND (b) the file
lives under `.github/workflows/`. Anything else (a bare 40-hex string in a
script, config, or docs file; a non-pinned `uses: org/action@main`; an
`env: API_TOKEN: <hex>` line in a workflow) is still caught.

## Why not just expand the exceptions file

The exceptions ledger is keyed on exact line CONTENT. Each new SHA is a
brand-new line, so every dependabot bump would have to also add an entry.
The ledger was already the largest moving part of the gate for workflows
(4 entries per file across 4 workflow files), and dependabot is the
canonical source of fresh 40-hex lines. Letting the SHAPER of the pattern
decide — i.e. matching the syntactic slot, not the literal token — is
strictly less work AND more legible than enumerating tokens.

## Why not a global 40-hex allowlist

A global allowlist would mask real leaked secrets anywhere in the tree.
The path gate keeps the bypass surgical: a 40-hex string shaped like an
action pin but living in a docs file, a Python script, a config, or a
markdown body is still red-flagged. (Tested by
`test_action_sha_outside_workflows_still_fails`.)

## What is deliberately left to another ticket

`tools/.public-clean-exceptions.json` still lists every existing
`uses: actions/...@<sha>` line. Those entries are now redundant — the
allowlist handles them — but removing them is a different change in a
file not in this ticket's `owns:`. They are also harmless: they only
suppress lines that the new logic would suppress anyway. A follow-up
should prune the now-dead entries to keep the ledger small.

## Acceptance check

- `PYTHONPATH=src python3 -m pytest -q tests/test_public_clean.py` →
  39 passed (was 34; added 5 new tests).
- `PYTHONPATH=src python3 -m charon.cli gate` → all checks passed.
- `python3 tools/check_public_clean.py` (whole-tracked-tree scan) →
  "public-clean OK", confirming the existing workflow SHA pins are no
  longer triggering the generic 40-hex pattern.
