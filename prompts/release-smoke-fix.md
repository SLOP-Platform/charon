Fix the `image-smoke` job in `.github/workflows/release.yml` so it actually exercises the
published image's DEFAULT surface — the token-gated GATEWAY — instead of the stale Mode-B service
surface. Canonical tier: **med** (fleet `sonnet`). Small, mechanical CI fix — do NOT touch product
code. Own ONLY `.github/workflows/release.yml`.

WHY (DOCKER-INSTALL #64 review finding, 2026-06-27):
The image default is now the GATEWAY. On master the `Dockerfile` already ends with
`EXPOSE 8080` and `CMD ["charon","gateway","--host","0.0.0.0","--port","8080"]`. But the
`image-smoke` job still does the OLD Mode-B smoke:
```yaml
docker run -d --name charon-rel -p 127.0.0.1:8473:8473 charon:ci
... curl -fsS http://127.0.0.1:8473/healthz ...
```
This is broken two ways for the gateway image, so the NEXT release's `image-smoke` would FAIL:
  1. The container serves the gateway on `:8080`, not `:8473`, and the gateway health path is
     `GET /v1/models` (token-gated), not `/healthz`.
  2. The CMD binds `--host 0.0.0.0` with NO token, so `build_server` RAISES
     `NonLoopbackBindWithoutToken` and the container refuses to start at all (a tokenless
     non-loopback bind is rejected by design).

WHAT TO DO (minimal change, keep the publish gate working):
Rewrite ONLY the `image-smoke` job's "run service + healthz" step (rename it to something like
"run gateway + /v1/models") to exercise the GATEWAY correctly:
  - Run the image with a `CHARON_GATEWAY_TOKEN` set, e.g.:
    ```yaml
    docker run -d --name charon-rel \
      -e CHARON_GATEWAY_TOKEN=ci-smoke-token \
      -p 127.0.0.1:8080:8080 charon:ci
    ```
    (Generate or hardcode any non-empty token — it only needs to satisfy the non-loopback-bind
    guard for an ephemeral CI container; a fixed literal like `ci-smoke-token` is fine.)
  - Poll `http://127.0.0.1:8080/v1/models` with the `Authorization: Bearer <token>` header and
    assert HTTP 200. The gateway returns 200 with an EMPTY model list before any provider/model is
    configured, so a clean image satisfies this. Prefer asserting the status code explicitly, e.g.:
    ```yaml
    for _ in $(seq 1 30); do
      code=$(curl -s -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer ci-smoke-token" \
        http://127.0.0.1:8080/v1/models) || true
      if [ "$code" = "200" ]; then ok=1; break; fi
      sleep 1
    done
    ```
  - Keep `docker logs charon-rel`, `docker rm -f charon-rel`, and the final
    `test "${ok:-0}" = "1"` pattern so a failure is loud and the container is always cleaned up.

MODE-B SERVICE SMOKE:
The old smoke only tested `/healthz` on `:8473`, which is NOT the image default anymore. Do NOT
re-create a second container just to chase the Mode-B `charon-service` profile unless it tests
something real and is cheap. If you keep ANY Mode-B check, it must run the service explicitly
(e.g. override the CMD to the service entrypoint and expose its port) and curl its real health
path — otherwise just DROP the `:8473`/`/healthz` smoke and leave a one-line comment in the job
noting the Mode-B service surface is covered elsewhere (it is exercised by the test suite in the
`gate` job). Default recommendation: replace the single Mode-B smoke with the gateway smoke above;
do not add complexity.

CONSTRAINTS:
  - Own ONLY `.github/workflows/release.yml`. No product/`src` changes, no other workflow files.
  - Do NOT alter the `gate` or `publish` jobs, the digest-pinning/provenance steps, the GHCR push,
    the `needs: [gate, image-smoke]` wiring, or the `runs-on: ${{ fromJSON(vars.CI_RUNNER ... ) }}`
    pattern. The publish step must stay gated on a GREEN `image-smoke`.
  - Product-clean (no SLOP/fleet/rig leak), agent/provider-agnostic.
  - Keep the YAML valid; if a linter/`actionlint` is available, run it.

Commit ALL work on your branch and STOP — do NOT push / open a PR / run submit.sh; the launcher
publishes after you exit. Write your review note as `docs/review-log/RELEASE-SMOKE-FIX.md`
recording WHAT you changed and WHY (cite the DOCKER-INSTALL #64 finding). If a fix needs a file
outside the owns list, STOP and run release.sh with a one-line reason.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
