# DOCKER-SMOKE-CLEANUP — review notes

## Summary
- **release.yml** (`image-smoke` job): Added `trap 'docker rm -f "$name" ...' EXIT` immediately after the run-scoped container name is set, so cleanup runs unconditionally on any exit path (not just the normal fall-through).
- **heavy.yml** (`image-smoke` job): Mirrored release.yml's pattern — run-scoped name (`charon-ci-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`), kernel-assigned host port (`-p 127.0.0.1:0:8473` read via `docker port`), and same trap-based cleanup.

## Review checklist
- [x] Trap uses single quotes — `$name` expands at trap time (EXIT), not at registration time.
- [x] heavy.yml no longer contains fixed `--name charon-ci` or fixed `-p 127.0.0.1:8473:8473`.
- [x] All `run:` blocks pass `bash -n` syntax check.
- [x] Python retry loop skipped (low lift but unnecessary diff; shell loop is consistent with release.yml).
- [x] No ACTION-PIN-POLICY refs remain (that ticket handles `uses:` pins; this ticket only touches shell `run:` blocks).
- [x] Scope: only `.github/workflows/release.yml` and `.github/workflows/heavy.yml` changed (plus this review fragment).
