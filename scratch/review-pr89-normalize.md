# Adversarial review — PR #89 `fix/normalize-case-quant` (NORMALIZE-CASE-QUANT-FIX)

Diff base: `origin/master...origin/fix/normalize-case-quant` (master @ 3b434dc).
Reviewed the branch diff, not the self-report. Read-only; working tree restored clean.

**Verdict: MERGE** (one non-blocking follow-up: wire the detector into the gate).

Files touched (4, all in scope): `src/charon/proxy.py`, `tests/test_normalize_model_id.py`
(new), `tools/check_catalog_case_quant.py` (new), `docs/review-log/NORMALIZE-CASE-QUANT-FIX.md` (new).

## What I verified (ran the code)
- Full suite with branch files: **1311 passed** (98s).
- New tests + SR-1 downgrade test together: **15 passed**.
- Detector on the live 16-id catalog: `OK (16 ids canonical, no collisions)`, exit 0.
- **Fail-on-revert**: reverted ONLY the `_normalize_model_id` body back to master's
  `return model_id.rsplit("/",1)[-1]` in an isolated copy →
  `test_quant_case_variant_is_not_downgrade` goes **RED**
  (`pseudo_success` True, note "silent downgrade: asked 'kimi-k2.7-code', got
  'Kimi-K2.7-Code'"), plus 4 unit asserts + the collision test. SR-1 stayed GREEN.

## Findings by severity

### CRITICAL — double-bill / SR-1 regression: NOT reintroduced ✓
`proxy.py:262-268`. The fold is applied AFTER the SR-1 final-segment rsplit:
`seg = model_id.rsplit("/",1)[-1].lower()` then loop-strip quant. The namespace
guard is untouched. `tests/test_proxy_downgrade.py` all pass and still mean
something — `test_fully_qualified_return_is_not_pseudo_success`
(`accounts/fireworks/models/deepseek-v4-pro` vs bare) still asserts no
pseudo_success, no double-bill. `classify` (proxy.py:324-325) normalizes BOTH
sides symmetrically. No regression.

### HIGH — #30 detector is present + tested but NOT wired anywhere (dormant)
`tools/check_catalog_case_quant.py` is functional (pure `find_mismatches()` +
`main()` exit 0/1/2, covered by 3 seeded unit tests) but is referenced by NOTHING
outside its own test: not in `tools/gates.json`, not in `gate_runner.CHECKS`
(`src/charon/gate_runner.py:6`), and it carries no `# @covers:` annotation — so
`check_gate_registry.py` does not flag it (confirmed why CI stays green: rule 5
only fails an ORPHAN `@covers`, not an unregistered tool). Net: directive #30
("mechanize catalog-mismatch detection") is only PARTIALLY met — the detector
will never run in CI/preflight; a future non-canonical catalog id would NOT be
caught automatically. The review-log documents this as a deliberate `owns:`-scope
deferral and it is a genuine ~1-line follow-up (append to `CHECKS` + a `gates.json`
entry + `@covers` tag). Non-blocking for THIS money-path fix, but the manager
should open the wiring follow-up immediately so #30 is actually enforced.

### LOW — over-normalization / false-merge risk: bounded, acceptable
The quant regex `-(?:fp8|fp16|fp32|bf16|int8|int4|q\d+(?:[._][0-9a-z]+)*)$`
(proxy.py:243-244) is an anchored allow-list, so name segments `-code`/`-pro`/
`-flash`/`-27b`/`-v4` are preserved (test_non_quant_suffix_preserved confirms).
`-q2-turbo` is NOT stripped (group needs `[._]` continuation, `-turbo` breaks it).
Residual theoretical false-merge only if a genuinely-distinct billable model's id
literally ended in a quant token (e.g. a hypothetical `foo-int8` that is a real
SKU distinct from `foo`). Live catalog has no such case and the detector guards
the curated catalog against exactly this collision. classify compares a single
expected vs returned (not cross-catalog), so the fold cannot mis-route between two
catalog entries at runtime. `_lookup_pricing` (proxy.py:395-398) could pick the
wrong price only under a catalog collision the detector is designed to block.
Acceptable.

### INFO — scope is clean
No stray edits; every file is within the ticket's stated `owns:`. Gate-wiring
correctly deferred rather than reaching into files owned elsewhere.

## Bottom line
Money-path fix is correct, the critical double-bill/SR-1 regression is provably
not reintroduced, fail-on-revert holds on a client-observable assertion, and scope
is tight. MERGE. Track the detector gate-wiring as an immediate follow-up so #30
is enforced rather than dormant.
