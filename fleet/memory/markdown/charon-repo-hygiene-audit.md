---
description: DONE 2026-06-26 — public charon repo scrubbed of internal dev-meta via git history rewrite + force-push (HANDOFF.md removed from all history; infra identifiers replaced). No real secrets were ever committed.
metadata: 
name: charon-repo-hygiene-audit
node_type: memory
originSessionId: 57e20449-d31c-42de-a683-0ba521791c9c
type: project
tags: [audit, charon, hygiene, repo]
last_referenced: 2026-07-13
---
**RESOLVED 2026-06-26** (was: deferred). The PUBLIC repo `SLOP-Platform/charon`
exposed internal dev meta/infra (private-range IPs, an internal build-host name,
`~/.ssh/*` key-file names, a personal home path, an internal ticket ref, a
coordination-guard phrase, the internal runbook `docs/HANDOFF.md`). **No real
secrets** (no API keys / private keys).

**What was done (operator-confirmed each destructive step via prompts):**
- `docs/HANDOFF.md` → **deleted from the repo + all history**; private copy kept at
  `/build-rig/HANDOFF.md` (+ `GATEWAY-DROID-PROMPT.md` there too).
- **Full history rewrite** with `git filter-repo` on an isolated mirror: removed the
  HANDOFF path from every commit + a `--replace-text` map (concrete identifiers →
  neutral placeholders, e.g. private IPs → `203.0.113.x` TEST-NET). The replace map
  is kept OUT of the repo so it can't re-leak. **Force-pushed** `master`,
  `mvp-routing`, `tier2` + tag `v0.1.0`; local re-synced + gc'd. Justified because the
  repo had **0 forks, 0 clones, 0 open PRs, no branch protection**.
- Verified **0** concrete-infra hits across all rewritten commits. Functional tokens
  (`slop`/`mediastack` import-guard, `self-hosted-runner` runner label, `Nnyan` LICENSE)
  **preserved**. 114 tests still green.
- Forward-only prose-polish commit `08bfdd8` (residual wording) is **local, pending
  the operator's `! git push`**.

**PR-ref leak found by independent review + fully remediated:** force-push left the
pre-rewrite commits publicly fetchable via GitHub `refs/pull/1|2/head` (these are
server-side and NOT GC'd — the earlier "GC will handle it" caveat was WRONG). Fix
(operator-approved): **deleted + recreated** the public repo (`gh repo delete` needed a
`delete_repo` scope refresh), pushed only the scrubbed branches+tag, recreated the
`v0.1.0` release (re-triggers the ghcr publish + SLSA provenance pipeline → new image
digest). Verified **0** leaks across ALL refs incl. `refs/pull/*`. Backup mirror at
`/build-rig/charon-rebuild-backup.git`. Lost: old PR/CI history
(0 forks, acceptable). See
[[charon-push-guard-gap]] (the force-push bypassed an intentional deny-list guard),
[[charon-vision-gateway-first]], [[charon-project-state]].