# KSF CLASS REGISTER — Historical failure CLASSES ranked by frequency × blast radius

Source: `KSF-CLASS-CORPUS.md` (2026-07-31 audit) — 30+ incidents condensed into 15
deduplicated classes. This is the requirements spec for any framework we converge on;
it outlives the KSF question.

**10 classes hit 3+ times with NO gate or no KSF gate.** Each GAP row is a
framework-technology gap a gate framework MUST address to be "load-bearing" for
this programme.

## RANKED REGISTER

| # | Class | Freq | Blast | Currently gated by? |
|---|---|---|---|---|
| 1 | **built-but-inert / built-not-wired** — code built, tested, merged green with ZERO callers | ~18 | HIGH | KSF `inert_code` EXISTS but UNREGISTERED in charon |
| 2 | **fake-green / vacuous gate** — gate reports GREEN on 0 items scanned, exit piped into void, RED path unreachable | ~15 | VERY HIGH | KSF `fail_loud`, `no_pipe_mask`, `no_vacuous` — slices, not comprehensive |
| 3 | **self-report-lie / false-success** — model/agent/tool claims SUCCESS when work was never done | ~12 | VERY HIGH | **NONE** — doctrinal adversarial review not mechanized |
| 4 | **config-siloing / multi-source-drift** — deployed config ≠ source in repo | ~10 | HIGH | fleet bash gate only (no KSF gate) |
| 5 | **finished-work-stranded / accumulated state rot** — finished branches never landed, PRs pile up, work rediscovered | ~8 | MEDIUM-HIGH | **NONE** |
| 6 | **hand-rolling / adopted-not-fully-used** — adopted tools used at <12% capability | ~20 | VERY HIGH | PARTIAL — substrate-first-gate covers build-vs-adopt decision, not depth-of-adoption |
| 7 | **effect-not-verified / post-state not checked** — assert exit code 0, not that desired POST-STATE exists | ~5 | HIGH | **NONE** — fixed instance-by-instance |
| 8 | **silent-client-degradation** — failures invisible to monitoring; dead pool fallback | ~5 | HIGH | **NONE** |
| 9 | **test-hygiene / tests-never-executed** — test files on disk never run in CI | ~5 | MEDIUM-HIGH | **NONE** |
| 10 | **wrong-verdict-from-wrong-ref** — two-dot diff lies; measurements against stale checkout | ~4 | HIGH | **NONE** |
| 11 | **duplicate-systems-across-repos** — per-repo forks of shared tooling; charon vendors KSF | ~5 | HIGH | KSF modules/ surface exists but unused cross-repo |
| 12 | **deploy-context-blind** — gate validates CODE not deploy target | ~4 | MEDIUM-HIGH | ADR only (not built) |
| 13 | **concurrency / isolation failures** — two agents on one checkout; worktree gate runs wrong code | ~6 | MEDIUM | PARTIAL — WORK-LEASE-GATE boarded, Faktory ADOPT-PARTIAL |
| 14 | **no-decision-time-gate** — check fires at session start, not at decision time | ~5 | MEDIUM | FIXED in rig (substrate-first-gate.sh), absent in KSF |
| 15 | **nondeterministic-gate / unbounded-fan-out** — verdict varies run-to-run on unchanged tree | ~4 | HIGH | PARTIAL — KSF has no reproducibility requirement |

## GAPS SUMMARY — 7 of top 10 classes no KSF gate

| Class | Incidents | Blast | Existing coverage |
|---|---|---|---|
| self-report-lie/false-success | 12+ | VERY HIGH | None |
| config-siloing/drift | 10+ | HIGH | fleet bash gate only |
| finished-work-stranded | 8+ | MEDIUM-HIGH | None |
| effect-not-verified | 5+ | HIGH | None |
| test-hygiene/orphaned-tests | 5+ | MEDIUM-HIGH | None |
| silent-client-degradation | 5+ | HIGH | None |
| wrong-verdict-from-wrong-ref | 4+ | HIGH | None |
| deploy-context-blind | 4+ | MEDIUM-HIGH | ADR only |
| duplicate-systems-cross-repo | 5+ | HIGH | modules/ surface unused |
| built-but-inert (de facto) | 18+ | HIGH | `inert_code` EXISTS but UNREGISTERED |

## KEY FINDINGS

1. **`inert_code` is unregistered in charon** — the gate that would catch the #1-ranked
   failure class exists but is not wired. The hypothesis that it's blocked by performance
   (120s timeout) is refuted: real runtime is 4.5s. The real blocker is noise: 200+ false
   positives from best-effort `_resolve_call()`.
2. **self-report-lie is the #1 un-gated VERY-HIGH-blast class** — 12+ incidents, no
   mechanized gate. Single highest-value gap.
3. **KSF's 9 gates cover important but narrow slices.** 70% of real incidents map to
   classes KSF cannot detect.

## PRUNE CANDIDATES (proposed, not to be done in this ticket)

| Gate | Rationale |
|---|---|
| `leak_guard` | Too broad — RFC1918/home paths trigger. gitleaks/pre-commit concern, not structural. |
| `wiring_alignment` | Too narrow — string-matches `import <module>` in tests/. Imported ≠ tested. |
