> ARCHIVED 2026-07-08 — superseded by RUNBOOK.md 'Release + redeploy runbook' (durable /data-volume + release/deploy/rollback steps salvaged; the v0.3.3->v0.3.4 version-specific body was a stale snapshot)

# Redeploy Plan — bring master's accumulated fixes live on 4-LOM

Prepared 2026-07-06. Read-only investigation only — nothing executed.

## 1. Current state (verified live via `ssh -i ~/.ssh/4lom stack@10.0.1.60`)

- Running container `charon-gateway-1`: image `ghcr.io/slop-platform/charon:v0.3.3`, `State.Health.Status = healthy`.
- Remote `/home/stack/charon/docker-compose.yml`: `gateway` service only, `container_name: charon-gateway-1`,
  volume `charon-config:/data` (external, name `charon_charon-config`) — config/secrets ARE on the named
  volume, not in the image. No `charon-service` entry remotely (fine — deploy.sh only drives `SERVICE=gateway`).
- `/data/pools.json`: dict keyed by model name, 50 top-level keys (matches `deploy.sh` default
  `EXPECTED_POOL_COUNT=50`). `deepseek-v4-pro` pool order:
  `["deepseek-v4-pro-ng", "deepseek-v4-pro-ds", "deepseek-v4-pro-or", "deepseek-v4-pro-go", "deepseek-v4-pro"]`
  — first entry is the nanogpt alias, consistent with `deploy.sh`'s hardcoded expectation that
  `X-Charon-Provider: nanogpt` for that model today.
- `/data/secrets.json`: all 9 required key envs present (`NANOGPT_API_KEY`, `GROQ_API_KEY`,
  `CEREBRAS_API_KEY`, `MISTRAL_API_KEY`, `TOGETHER_API_KEY`, `OPENROUTER_API_KEY`, `NEURALWATT_API_KEY`,
  `DEEPSEEK_API_KEY`, `OPENCODE_ZEN_KEY`).
- `docker compose` v5.2.0 present; `/` has 423G free — no disk-pressure risk for image pulls/backups.

**Important discrepancy vs. the briefing:** the deployed image is already **v0.3.3**, not an older
version. The gap is NOT a stale deployed tag — it's that **20 commits landed on `origin/master`
(`b898ac4`) after the `v0.3.3` tag (`ec0d8ae`) without bumping `pyproject.toml`'s `version = "0.3.3"`**.
So the `v0.3.3` GHCR image genuinely predates: the failover-401 classification + synthesized 503
`all_providers_exhausted` fix, PR #5's request-normalizer (strip `reasoning_content` from inbound
messages), PR #6's auto-derived `cost_rank`/`cost_class` gating, the salvaged public-clean lint tool,
and the per-session cost counter (`X-Charon-Session` + `GET /charon/cost`). None of this is live yet.

## 2. `fleet/deploy.sh` safety review

Read line-by-line; `bash -n` passes (no syntax errors).

**Sequence confirmed correct:**
1. Preflight (before touching anything): pool-count check against `EXPECTED_POOL_COUNT`, `verify_keys_present`,
   `verify_deepseek_provider` (live curl call, checks `X-Charon-Provider: nanogpt`).
2. `backup_data()` — tars the named `/data` volume via a throwaway container using the *current* image,
   to `.charon-deploy-backups/data-<ts>-<prev>-to-<new>.tar`, `chmod 600`, asserts non-empty.
3. `trap rollback ERR` set only AFTER the backup exists (correct — nothing destructive happens pre-backup, so
   no rollback machinery is needed for preflight failures).
4. Pull new tag → write compose override (only overrides `image:`, not volumes) → `compose up -d gateway`.
5. `verify_all`: `wait_healthy` (Docker's own image-level `HEALTHCHECK`, confirmed present in
   `Dockerfile:117` and independently in local `docker-compose.yml`'s `healthcheck:` block — will report
   `healthy`/`unhealthy` correctly even though the *remote* compose file has no explicit healthcheck override,
   because Docker falls back to the image's built-in probe), pool-count-unchanged, keys-present,
   deepseek-v4-pro provider unchanged.
6. On ANY `ERR` after the trap is armed: `rollback()` captures the failing exit code, pulls the previous tag,
   stops the service, **wipes `/data` and restores it from the just-made backup**, brings the service back up
   on the old tag, and re-runs `verify_all` against the pre-deploy pool count — then re-raises the original
   failure's exit code (or logs "ROLLBACK VERIFY FAILED; backup remains at $backup" if the rollback itself
   doesn't verify clean, without deleting the backup).
7. Named volume mount means normal (non-rollback) `compose up -d` never touches `/data` content at all —
   config/secrets persist automatically across the image swap; the backup/restore machinery only fires on
   the rollback path.

**Gaps / things to be aware of (none block using it, but worth knowing before the first live run):**
- `verify_deepseek_provider` makes a real, billed request to a live provider (nanogpt) on *every* deploy,
  including the preflight check — i.e., every invocation of `deploy.sh` (even one that ultimately fails
  preflight) burns at least one live completion call. Low cost, but not free, and not something to invoke
  repeatedly just to "test the script."
- The nanogpt-is-primary-for-deepseek-v4-pro expectation is hardcoded, not derived from `pools.json`. If pool
  ordering/aliasing for that model is ever changed as a deliberate config edit, this check will start
  failing and trigger an unwanted rollback — worth a comment in deploy.sh, not urgent to fix now.
- Preflight failures (before `backup_data`) abort via bare `set -e`, no rollback attempted or needed — correct,
  but means a preflight failure leaves the operator with only the raw remote stderr, no "already rolled back"
  reassurance. Acceptable since nothing was changed.
- No dry-run/`--check` mode — first invocation against 4-LOM is inherently a real deploy attempt (with
  functioning auto-rollback). Given the design review above, this is an acceptable, well-guarded first use,
  not a blocker.

**Verdict: no fixes required before running it.** The script backs up first, verifies four independent
signals post-deploy, and auto-rolls back + restores the backup on any failure, before re-raising the
original error. It has never been run live, so the recommendation is still to run it once against a
non-critical tag path first if the operator wants extra confidence (e.g., deploy the *same* `v0.3.3` tag
that's already running, to dry-run the full mechanics with zero version delta) before deploying the real
new tag.

## 3. Release path confirmation (`.github/workflows/release.yml`)

Confirmed: triggers on `push: tags: v*` AND `release: published`, concurrency-grouped per ref. `publish` job
`needs: [gate, image-smoke]` — an untested image can never publish. `derive version` step reads
`pyproject.toml` and **hard-fails if `GITHUB_REF_NAME` (the pushed tag) doesn't match the pyproject version**
— so the tag and the version bump must be the same commit's state before tagging. Base image digest is
pinned fresh at build time; only the immutable `:vX.Y.Z` tag is pushed (never `:latest`). Runs on the
self-hosted 4-LOM runner via the `CI_RUNNER` repo variable.

So the release path is real and does what's needed: **bump `pyproject.toml` → commit/push → tag `vX.Y.Z` →
push tag → CI (`gate` + `image-smoke` + `publish`) builds and publishes `ghcr.io/slop-platform/charon:vX.Y.Z`
→ then, separately, `deploy.sh vX.Y.Z` on 4-LOM.**

## 4. Recommended version bump: **0.3.4** (not 0.4.0)

Rationale: all 20 pending commits are bug fixes and additive, backward-compatible features (failover
classification fix, message-normalization fix, cost_rank/cost_class derivation, a lint tool, a read-only
cost-tracking endpoint) — no removed/renamed public surface, no config-format break. The one behavior change
a client could notice is the failover path now synthesizing a terminal `503 all_providers_exhausted` instead
of whatever it did before (a wrapped/unknown 401 passthrough) when every provider is exhausted — this is a
bug fix to the client-visible contract (previously a confusing/wrong error), not a breaking change to the
API shape itself (still an HTTP error response). That doesn't rise to a minor "feature line" bump on its own;
it doesn't warrant 0.4.0. Treat 0.4.0 as the next checkpoint once a genuinely new capability (e.g., the
in-tree work-engine, or WCI) ships.

## 5. Ordered release + deploy plan

1. **Bump version**: edit `pyproject.toml` line 7, `version = "0.3.3"` → `version = "0.3.4"`, on `master`
   (or a short-lived bump branch merged to master first — operator's call on branch protection).
2. Commit: `git commit -am "chore(release): bump version to 0.3.4"`.
3. Push to `origin/master` (normal PR/merge or direct push per repo's existing convention — this repo's
   history shows version bumps go straight to master).
4. Tag: `git tag v0.3.4` on the bump commit.
5. Push the tag: `git push origin v0.3.4` — this alone triggers `release.yml` (tag-push trigger), no GitHub
   Release object required (SR-10 note in the workflow: tag push publishes independently of a Release).
6. Watch the run: `gate` (lint/type/tests/boundary/version-consistency) → `image-smoke` (build + smoke) →
   `publish` (build-push-action to `ghcr.io/slop-platform/charon:v0.3.4` + SLSA attestation). Confirm all
   three jobs green before touching 4-LOM.
7. Confirm the tag actually pushed to GHCR (`gh api` or the Packages tab) and matches the intended commit.
8. **Only once 6-7 are confirmed green**, deploy: `bash /home/stack/charon-private/fleet/deploy.sh v0.3.4`.
   Optionally, if extra confidence is wanted first: `bash deploy.sh v0.3.3` (redeploy the currently-running
   tag) as a zero-risk dry run of the full backup/verify/rollback mechanics before the real jump to v0.3.4.
9. Watch deploy.sh's own log output — it reports pull, backup path, health/verify results, and either
   "deploy complete: v0.3.3 -> v0.3.4" or a rollback with the retained backup path on failure.
10. Post-deploy spot check from the operator's own machine (not required by the script, but cheap
    reassurance): hit `/v1/models` and one real chat completion through the gateway as normal daily use.

## 6. Plan location

`/home/stack/charon-private/fleet/REDEPLOY-PLAN.md` (this file).
