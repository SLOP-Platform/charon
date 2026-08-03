# Review: PR-AUTOMATION-EVAL

**Date:** 2026-08-01
**Reviewer:** plo-koon (EVAL lane — measure and report, wired nothing)
**Type:** design-review (comparative evaluation)

## Verdict
ADOPT (wrap) — see `fleet/state/PR-AUTOMATION-EVAL.md` for the full long-form.

## Decision summary
- **ADOPT (wrap) The-PR-Agent/pr-agent** as the diff→findings engine (MIT, self-hosted, arbitrary
  OpenAI-compatible `api_base` via litellm → routes through the Charon gateway, Gitea support).
  Retire the engine slice (~250 lines) of `fleet/review-pool.sh`; keep the thin claim/queue +
  reviewer!=builder-over-OUR-droid-ids shell + Manager-dispensation firewall.
- **REJECT aider** for this problem (build client, not a reviewer; no gap vs `opencode`).
- **REJECT SaaS-only** candidates (CodeRabbit/Greptile/Reviewpad/Sourcery/Qodo-hosted): no arbitrary
  OpenAI-compatible base URL, no self-host — fail rule #5 on fit, not capability.
- **No candidate ships an MCP server** (verified in source) — MCP-first is not satisfiable here;
  integration shape is CLI-under-our-claim-layer.

## Key measured findings (evidence in the owned file)
- The hand-roll's B1 is **still structurally inert on the SLOP-Platform/charon mirror**: open PRs there
  are authored `charon-bot`/`Nnyan` (verified #214/#215/#216), compared against per-droid
  `CHARON_DROID_ID` — disjoint namespaces, guard never fires. The B1 test fabricates matching values
  (`GH_MOCK_AUTHOR=strong-abc123`), so it never exercises the real identity path.
- B3 is **still not met**: `review-pool.test.sh` is not in `CI_SUITES` (`grep -c review-pool
  fleet/checks/rig-ci-scope.sh` = 0) — it never runs in CI.
- The pool DID run in production today (2026-08-01, saba-rv* droids): ~17 PRs claimed/marked-done, and
  **every verdict is a BOUNCE on "CG review engine failed (rc=3)"** (quarantined at
  `fleet/state/review-quarantine-saba/`). Zero usable verdicts to date. The queue file is empty at
  sample time — "queue never populated" is accurate only at that instant.
- #313-fixture-bypass / #188-dead-no-op are **LLM-semantic catches, not tool guarantees**: both tools
  depend on the model+prompt+repo-context. pr-agent (repo-context + structured output) is the
  better-equipped of the two; the deterministic fix for that class is mutation testing (already the
  rig's fixture-bypass/gate-integrity machinery), not a review tool.
- **Neither tool reduces time-to-merge by itself** — the 46-PR backlog is a merge-policy problem
  (auto-merge on green / batch-merge pass), orthogonal to the reviewer.

## Status
Pending Manager dispensation. EVAL-REGISTRY rows for this verdict are in the owned file §6 and must be
appended to `fleet/state/EVAL-REGISTRY.md` by the manager (registry is outside this ticket's owns:).
Runtime AP-12 trial (3 real PRs through our gateway) is deferred and is the pre-wire gate.
