---
description: "Charon hosting decision (public GitHub SLOP-Platform org) + shared self-hosted-runner self-hosted runner — with a COLLISION GUARD: another session owns runner setup."
metadata: 
name: charon-hosting-and-runner
node_type: memory
originSessionId: 167ea4b7-b9f5-4546-ab7c-ebb4bbb8d9f6
type: project
tags: [charon]
last_referenced: 2026-07-13
---
**Decision (operator, 2026-06-25):** Charon is hosted as a **PUBLIC** repo in the
GitHub org **`SLOP-Platform`** (`github.com/SLOP-Platform/charon`), CI on a
**shared self-hosted runner** (zero GitHub Actions minutes). GitLab was tried and
**abandoned** (SSH/token/CI-dialect/UI friction). Rationale that settled it:
private GitHub repos are free; only Actions minutes cost; public repos get
unlimited free Actions; the `SLOP-Platform` grouping is just a free GitHub org.

**⚠️ COLLISION GUARD (do not violate):** a separate **mediastack** session owns
ALL self-hosted-runner / runner / org-runner setup (ticket #1318). This Charon work must **NOT**
register runners or touch org runner settings — it ONLY creates the repo +
`.github/workflows/*.yml` that **use** the `[self-hosted, self-hosted-runner]` org runner pool.
If the org runners aren't online yet, pipelines just QUEUE — coordinate timing
with the operator; never stand up your own runner.

**self-hosted-runner runner (read-only facts):** `<COORDINATOR_HOST>`, Ubuntu 24.04, ssh alias
`mediastack`, user `stack`, has Docker+buildx + Python 3.12 + libicu.

**Workflow gotchas proven on mediastack — bake into Charon's workflows:**
1. Ubuntu runner ⇒ `actions/setup-python` `python-version: "3.12"` works.
2. If using actionlint, add `self-hosted-runner` to `.github/actionlint.yaml`
   (`self-hosted-runner.labels: [self-hosted-runner]`) or it errors "unknown label".
3. Install CLI tools to `$RUNNER_TEMP/bin` + `echo "$RUNNER_TEMP/bin" >>
   $GITHUB_PATH` — never root-owned `/usr/local/bin`.
4. Don't set `PYTEST_ADDOPTS=--basetemp=$RUNNER_TEMP/...` if there are
   hermeticity/tmp-allowlist checks.
5. Verify ONE gate goes green on the runner before pointing everything at it.
Reference mediastack's `.github/workflows/*.yml` for working patterns.

**Process:** repo `SLOP-Platform/charon` exists; visibility is PUBLIC. Remote +
unwind work done — see the DONE update below. Full §9 spec in `docs/HANDOFF.md`.
See [[charon-project-state]]. `git push` is harness-gated → hand the operator `!`.

**UPDATE 2026-06-25 (transfer):** the GitHub repo was **transferred**
`Nnyan/charon` → **`SLOP-Platform/charon`**; `e1bd94e` landed there via redirect,
so all `mvp-routing` commits were already in the org repo before this session.

**DONE 2026-06-25 (this session, commit 1546e6c — UNWIND landed locally):** all of
§9 except the push is complete. `origin` now `git@github.com:SLOP-Platform/charon.git`
(SSH verified reachable, `gitlab` remote removed); repo confirmed PUBLIC; tree
audited — no private/dev files tracked (caches/dist/.venv/.claude all gitignored),
nothing to scrub. `.gitlab-ci.yml` deleted; workflows: `ci.yml` (fast gate,
push/PR), `heavy.yml` (slow suites: Mode-A wheel-isolation, image-smoke,
pip-audit — schedule+dispatch), `release.yml` (GHCR publish on Release, GitHub
SLSA provenance restored), all `runs-on: [self-hosted, self-hosted-runner]`; `actionlint.yaml`
declares the self-hosted-runner label (actionlint clean). All gitlab→github/ghcr URLs
redirected; REVIEW-LOG reconciled. Gotchas 1–4 baked in.

**SHIPPED 2026-06-26:** pushed; **PR #2 merged to master** (f83d697). The self-hosted-runner
runner IS online (`actions-runner-3`, host `stack`, Python tool-cache 3.12.13) and
picks up jobs (it's shared/single, so runs occasionally QUEUE briefly when the
mediastack session is using it — normal). **CI GREEN** (run 28217434201, §9a gotcha
5 satisfied). **First GHCR publish DONE:** v0.1.0 release → `release.yml`
(gate+image-smoke+publish all green, run 28217548479) → `ghcr.io/slop-platform/charon:v0.1.0`
(`@sha256:a6e8f7c472b49b…`) with GitHub-native SLSA provenance (Rekor + repo
attestation + registry). **CI-fix needed first:** bare `pytest` console script
doesn't add CWD to sys.path → `tools.*` import failed on the runner; fixed with
`pythonpath = ["."]` in pyproject (commit 9e42cf4). GHCR package `charon` is now
**PUBLIC** — anonymous `docker pull ghcr.io/slop-platform/charon:v0.1.0` resolves
(verified HTTP 200 from the VM). GOTCHA: org `SLOP-Platform` defaulted to
Private-only packages ("Setting is disabled by organization administrators" in the
package visibility dialog even for an org owner); operator had to allow Public at
Org Settings → Packages → Package creation, THEN flip the package's own Danger
Zone → Change visibility → Public. New container packages default Private; future
ones need the same per-package flip (org policy now permits it). Operator's gh
token now has `read:packages` (added 2026-06-26). Minor future cleanup: actions
emit Node20-deprecation warnings (bump checkout/setup-python/build-push/attest
action majors when convenient).
