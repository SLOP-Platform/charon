repo: charon
tier: economy
difficulty: 1  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: ci-infra
branch: chore/docker-smoke-cleanup
depends_on: ACTION-PIN-POLICY
real-dep: ACTION-PIN-POLICY shared-file hand-off — that ticket is a live (not-done) owner of
  the SAME release.yml and heavy.yml this ticket edits (converting first-party `uses:` pins).
  Serialize behind it rather than run as a concurrent second writer of either file; rebase
  onto its merge before starting.
owns: .github/workflows/release.yml, .github/workflows/heavy.yml
accept: grep -q "trap 'docker rm -f" .github/workflows/release.yml && grep -q 'charon-ci-${GITHUB_RUN_ID}' .github/workflows/heavy.yml
prompt: /home/stack/charon-private/fleet/board/briefs/DOCKER-SMOKE-CLEANUP.md
scope: Fragility finding #6. `release.yml`'s `image-smoke` job (lines ~86-104) already uses
  a run-scoped container name (`charon-rel-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`) and a
  kernel-assigned host port, but cleanup (`docker rm -f "$name"`) only runs on the normal
  fall-through path immediately before the final `test "${ok:-0}" = "1"` line — the
  `run:` step executes under GitHub Actions' default `bash -eo pipefail`, so any unexpected
  early failure between `docker run` and that line (e.g. `docker port` returning empty,
  a `curl`/`sed` crash outside the retry loop's own `|| true`) skips cleanup and leaks the
  container on the shared self-hosted 4-LOM runner. Add
  `trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT` immediately after `name=...` is
  set, so cleanup runs unconditionally; the existing explicit `docker rm -f "$name"` before
  the `test` line can stay (idempotent) or be dropped now that the trap covers it.
  `heavy.yml`'s `image-smoke` job (lines ~58-70) has NEITHER a dynamic name nor a dynamic
  port — it hardcodes `--name charon-ci -p 127.0.0.1:8473:8473`, so two `heavy.yml` runs (or
  a `heavy.yml` run overlapping a stale leaked container) collide with "name already in use"
  / "port is already allocated". Mirror `release.yml`'s pattern exactly: run-scoped name
  (`charon-ci-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`), kernel-assigned host port
  (`-p 127.0.0.1:0:8473`, read back via `docker port`), and the same `trap`-based cleanup.
  Where it's a small lift, prefer a Python stdlib `urllib.request` retry loop over the
  `curl`+`sleep` shell loop for the HTTP smoke check (no new dependency; `python3` is already
  on the runner) — but do not block the ticket on this if it complicates the diff.
note: Standard review, mechanical. Sequenced behind ACTION-PIN-POLICY (see real-dep above),
  not because of any functional coupling — purely to avoid two concurrent writers of
  release.yml/heavy.yml. Fleet auto-claims once that ticket merges+done.sh.
