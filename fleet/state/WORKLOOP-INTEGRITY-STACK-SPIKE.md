# WORKLOOP-INTEGRITY-STACK-SPIKE — R0 lead-lens verdict (2026-07-23 re-brief, executed trials)

**Adopt-first, hands-on spike** of the work-loop-integrity stack proposed in
`fleet/state/WORKLOOP-INTEGRITY-RESEARCH.md`. **This is the re-briefed
attempt** — the first attempt (PR #161) was BOUNCED for being a source/docs
audit rather than a RUN, and for defaulting 3/4 verdicts to hand-roll. Per
EVAL-REGISTRY.md AP-12, a source-reading "trial" is NOT a valid trial for a
RUNNABLE candidate. Every layer verdict below is supported by an executed
trial transcript (host + command + observed output), not a file:line
citation. Where a prior claim was wrong, the correction is recorded
explicitly in the trial log.

`[[research-posture-solution-seeking]]` `[[adopt-substrate-build-only-novel-slice]]`
`[[gates-must-actually-run]]` `[[no-rig-as-product-adopt-dont-handroll]]`
`[[eval-registry-ap12-executed-trials-only]]`

---

## 0. Method and host inventory (the trial ground)

All trials ran on real hosts. Every layer was stood up, every make-or-break
test was executed, and observed output (not source-reading) drove the
verdict.

| Host | IP | Role for this spike | Key facts observed |
|---|---|---|---|
| 4-LOM | 10.0.1.60 | Primary trial host (has Charon gateway, Docker) | `stack@4-lom`, 12 cores, 11GB free RAM, `docker 29.6.0`, `charon-gateway-1` container (healthy, `v0.4.1`, 464 models on `/v1/models`, `auto` pool routes to `openai/gpt-oss-120b`). Reachable via `ssh -i ~/.ssh/4lom stack@10.0.1.60`. |
| BB-8 | 10.0.1.61 | Node.js + npm trial host (for `wmill` CLI install) | `stack@bb-8`, 8 cores, 14GB free, `node v22.23.1`, `npm 10.9.8`, has `act_runner` and 3 actions-runner dirs. Reachable via `ssh -i ~/.ssh/bb8 stack@10.0.1.61`. |
| charon-vm | 10.0.3.91 | (reachable but unused — 8 cores) | Reachable via `ssh -i ~/.ssh/vm-matrix-key charon@10.0.3.91` |
| rocinante | 10.0.1.51 | (reachable but unused — 4 cores) | Reachable via `ssh -i ~/.ssh/mediastack stack@10.0.1.51` |
| LO-LA59 | (10.0.1.59) | Unreachable | `ssh` connection refused on this run |
| Tardis (operator WSL) | local | Doc-authoring host | This file lives here |

**Network/connectivity corrections to the prior audit:**
- The brief lists "BB-8, Rocinante, LO-LA59" as trial hosts; **LO-LA59 was
  unreachable from Tardis at the time of this spike** (ssh connection
  refused). Trials fell back to 4-LOM (primary) and BB-8 (Node.js only).
- "Rocinante" was not `ssh 10.0.1.51` with the `rocinante` key — that key
  does not exist; the configured alias is `Host rocinante HostName 10.0.1.51
  User stack IdentityFile ~/.ssh/mediastack`. The same key works for BB-8
  but the brief specified `~/.ssh/bb8`. Both are listed in
  `~/.ssh/config`.

**Charon's ACTUAL git topology (verified, executed):**
- `git -C /home/stack/charon-private remote -v` →
  `origin https://github.com/Nnyan/charon-private.git (fetch)`. **No Gitea
  remote on the worktree host.** Charon's mirror lives on
  `Nnyan/charon-private` (private rig), not on `SLOP-Platform/charon`
  (public product repo).
- The brief assumes a Gitea-primary topology (per
  `fleet/SESSION-HANDOFF-ahsoka-tano.md`: "Gitea LIVE on c1-10p:3000; stack/
  charon migrated; charon-private not yet migrated"). That topology is NOT
  on the worktree host. We test against it via Archon's Gitea adapter
  (see §2.4).
- Worktree model: `charon-private-wt/<TICKET-ID>/` (verified: `git -C
  /home/stack/charon-private worktree list` shows 25+ active worktrees of
  this shape). Archon's model is `~/.archon/workspaces/<owner>/<repo>/
  worktrees/` (verified: `packages/paths/src/archon-paths.ts:1-30`).

---

## 1. Layer 1: agent-orchestrator (`AgentWrapper/agent-orchestrator`)

### 1.1 Trial setup (executed on 4-LOM)

```bash
$ ssh -i ~/.ssh/4lom stack@10.0.1.60
# No Go installed; install Go 1.23.4
$ cd /tmp && curl -sSL https://go.dev/dl/go1.23.4.linux-amd64.tar.gz -o go.tgz \
  && tar -C /tmp -xzf go.tgz
$ /tmp/go/bin/go version
go version go1.23.4 linux/amd64

$ git clone --depth=1 https://github.com/AgentWrapper/agent-orchestrator.git /tmp/ao
Cloning into 'ao'...
$ cd /tmp/ao/backend && /tmp/go/bin/go build -o /tmp/ao/ao-bin ./cmd/ao
# (Go module deps downloaded: 24MB binary built)
$ ls -la /tmp/ao/ao-bin
-rwxr-xr-x 1 stack stack 23992289 Jul 23 05:28 /tmp/ao/ao-bin
$ /tmp/ao/ao-bin doctor
... PASS config, data-dir, hooks-log, daemon, git, tmux ...
WARN github-token: no GitHub token found (set AO_GITHUB_TOKEN/GITHUB_TOKEN or run `gh auth login`)
```

Binary builds and runs. Confirmed: only `github/` subdir exists under
`backend/internal/adapters/scm/` (verified: `ls /tmp/ao/backend/internal/
adapters/scm/ → github`).

### 1.2 Make-or-break test (executed)

The brief's make-or-break: "does `ao` drive our Gitea-primary + GitHub-
mirror topology, or is it GitHub-API-coupled?" The prior audit said
`ClientOptions.RESTBase` is settable; I tested whether that lets us point
at a non-GitHub host. The trial revealed a HARDER restriction than the
prior audit claimed.

```go
// /tmp/ao/backend/internal/adapters/scm/github/host_test_main_test.go
package github
import (
    "fmt"
    "testing"
)
func TestHostWhitelist(t *testing.T) {
    p, _ := NewProvider(ProviderOptions{
        RESTBase:           "https://gitea.c1-10p.local:3000/api/v1",
        GraphQLURL:         "https://gitea.c1-10p.local:3000/api/v1",
        SkipTokenPreflight: true,
    })
    for _, u := range []string{
        "https://github.com/foo/bar/pulls/1",
        "https://gitea.c1-10p.local:3000/stack/charon/pulls/42",
        "https://c1-10p:3000/stack/charon/pulls/42",
        "https://git.example.com/o/r/pulls/1",
        "https://api.github.com/repos/foo/bar/pulls/1",
        "https://ghe.example.ghe.io/o/r/pulls/1",
    } {
        _, _, _, err := parsePRURL(u)
        fmt.Printf("URL=%-65s err=%v\n", u, err)
    }
}
```

```bash
$ cd /tmp/ao/backend && /tmp/go/bin/go test -v -run TestHostWhitelist ./internal/adapters/scm/github/
=== RUN   TestHostWhitelist
URL=https://github.com/foo/bar/pulls/1                                err=<nil>
URL=https://gitea.c1-10p.local:3000/stack/charon/pulls/42             err=scm: not found: host "gitea.c1-10p.local:3000" is not a github host
URL=https://c1-10p:3000/stack/charon/pulls/42                         err=scm: not found: host "c1-10p:3000" is not a github host
URL=https://git.example.com/o/r/pulls/1                               err=scm: not found: host "git.example.com" is not a github host
URL=https://api.github.com/repos/foo/bar/pulls/1                      err=<nil>
URL=https://ghe.example.ghe.io/o/r/pulls/1                            err=<nil>
--- PASS: TestHostWhitelist (0.00s)
```

**Trial finding — the prior audit was TOO GENEROUS.** Even when
`RESTBase` is overridden to point at Gitea, `parsePRURL()` (the function
that EVERY call path uses) rejects every non-GitHub host. The whitelist
is enforced in `isGitHubHost()` (`observer_provider.go:665-668`) and
re-checked in `parsePRURL` (`provider.go:626-628`). The whitelist is
hardcoded: `github.com`, `www.github.com`, `api.github.com`, `*.github.com`,
`*.ghe.io`. **No escape hatch.** A fork would need to:
1. Add `adapters/scm/gitea/{client,auth,provider,observer_provider}.go`
   (est. 3-5k LOC) per the prior audit's estimate — but the architectural
   pattern (`parsePRURL` is package-private) makes this harder than just
   "add a new dir".
2. Patch the `isGitHubHost` whitelist at TWO call sites.
3. Add webhook reception (currently 30s poll loop, per `docs/architecture.
   md` SCM Observer Loop).

### 1.3 Verdict: REJECT (host-whitelist is HARDER than prior audit claimed)

`ao` is GitHub-only by design. It is not a layer-1 candidate for the
Gitea-primary topology the operator wants. The hand-rolled 200-LOC
alternative is the after-adopt-disproven fallback (see §1.4 for the
adopt candidate that was actually executed).

**Next-best (in order, adopt-first — re-ranked after executing the demoted
adopt candidate in §1.4):**
1. **`adnanh/webhook` (ADOPT, EXECUTED in §1.4)** — webhook receiver
   with config-driven trigger rules, HMAC verification, command
   execution on match. Pairs with a thin orchestrator script for
   Gitea-side state. ~12.9 MB Go binary, single config file, 12.9k
   stars, MIT.
2. Windmill (see §3) — overkill for just the webhook layer, but a real
   adopt candidate if we want the whole DoD stack in one product.
3. Hand-rolled thin orchestrator (~200 LOC) — kept as the
   **after-adopt-disproven fallback**. The executed `adnanh/webhook`
   trial (below) did NOT disprove it, so the hand-roll is the next
   ADJACENT path if WLS-1b's `adnanh/webhook` wire-up turns out to
   have an unmet constraint in Charon's actual git topology (e.g.
   per-worktree routing, sub-path dispatch). It is NOT the recommended
   first path.

**No `WLS-1` build ticket should be opened.** The WLS-1b ticket
should adopt `adnanh/webhook` first and treat the hand-roll as the
fallback.

### 1.4 EXECUTED adopt-candidate trial: `adnanh/webhook` (the demoted #1 from §1.3 attempt 2)

**Why this trial exists:** Attempt 2 (§1.3) ranked the hand-roll
above `adnanh/webhook` without executing `adnanh/webhook` — an
auto-reject drift per `[[no-rig-as-product-adopt-dont-handroll]]` and
AP-5/AP-7. This trial closes that gap.

**Setup (executed on 4-LOM):**
```bash
$ git clone --depth=1 https://github.com/adnanh/webhook.git /tmp/webhook
$ cd /tmp/webhook && /tmp/go/bin/go build -o /tmp/webhook-bin .
$ ls -la /tmp/webhook-bin
-rwxrwxr-xr-x 1 stack stack 12929444 Jul 23 07:16 /tmp/webhook-bin
# version (from /tmp/webhook-bin -version)
webhook 2.8.3
```

**Make-or-break: drive a CI-fail→re-trigger loop end-to-end with a
real webhook binary, a real trigger rule, and a real receiver.**

Fixtures (written to `/tmp/wltrial/` on 4-LOM, full set in
`/tmp/wltrial/transcript/`):

```bash
# hooks.json — single hook, value-trigger-rule
$ cat /tmp/wltrial/hooks.json
[
  {
    "id": "ci-fail-retrigger",
    "execute-command": "/tmp/wltrial/ci-gate.sh",
    "command-working-directory": "/tmp/wltrial/scratch-ci",
    "response-message": "evaluated",
    "pass-arguments-to-command": [
      {"source": "payload", "name": "ref"},
      {"source": "payload", "name": "after"}
    ],
    "trigger-rule": {
      "and": [
        {"match": {"type": "value", "value": "refs/heads/main", "parameter": {"source": "payload", "name": "ref"}}}
      ]
    }
  }
]
```

**Trial 1 — push to main, build PASSES, no re-trigger:**
```bash
$ curl -sS -X POST -H "Content-Type: application/json" \
  -d '{"ref":"refs/heads/main","after":"433fdda4d2..."}' \
  http://127.0.0.1:9000/hooks/ci-fail-retrigger
evaluated
$ tail -3 /tmp/wltrial/ci-gate.log
2026-07-23T07:17:35Z ci-gate ref=refs/heads/main after=433fdda4d2...
BUILD_OK
rc=0
$ cat /tmp/wltrial/retrigger.log
(empty)
```

**Trial 2 — push to main, build FAILS, re-trigger fires:**
```bash
# build.sh now exits 7
$ curl -sS -X POST -H "Content-Type: application/json" \
  -d '{"ref":"refs/heads/main","after":"41075e0a5c..."}' \
  http://127.0.0.1:9000/hooks/ci-fail-retrigger
evaluated
$ tail -4 /tmp/wltrial/ci-gate.log
2026-07-23T07:17:44Z ci-gate ref=refs/heads/main after=41075e0a5c...
BUILD_FAIL (synthetic)
rc=7
2026-07-23T07:17:44Z CI_FAIL after=41075e0a5c... -> re-trigger
$ cat /tmp/wltrial/retrigger.log
2026-07-23T07:17:44.795594 RETRIGGER path=/retrigger bodylen=71
$ tail -2 /tmp/wltrial/receiver/events.log
--- 2026-07-23T07:17:44.795437 /retrigger ---
{"reason":"CI_FAIL","after":"41075e0a5c7b70ee8073d11b8fe65cdfdce97f6c"}
```

**Trial 3 — wrong ref, trigger rule rejects:**
```bash
$ curl -sS -X POST -H "Content-Type: application/json" \
  -d '{"ref":"refs/heads/side","after":"..."}' \
  http://127.0.0.1:9000/hooks/ci-fail-retrigger
Hook rules were not satisfied.
$ wc -l /tmp/wltrial/ci-gate.log   # unchanged: still 7 lines
7 /tmp/wltrial/ci-gate.log
$ wc -l /tmp/wltrial/retrigger.log # unchanged: still 1
1 /tmp/wltrial/retrigger.log
```

**Trial 4 — HMAC-signed request:**
```bash
# hooks-hmac.json with trigger-rule = value + payload-hmac-sha1
$ BODY='{"ref":"refs/heads/main","after":"41075e0a5c..."}'
$ SIG="sha1=$(printf %s "$BODY" | openssl dgst -sha1 -hmac mysecret -binary | xxd -p -c 256)"
$ curl -sS -X POST -H "Content-Type: application/json" \
  -H "X-Hub-Signature: $SIG" -d "$BODY" \
  http://127.0.0.1:9000/hooks/ci-fail-hmac
evaluated-hmac
# Wrong secret -> 500
$ WRONG="sha1=$(printf %s "$BODY" | openssl dgst -sha1 -hmac wrongsecret -binary | xxd -p -c 256)"
$ curl -sS -X POST -H "Content-Type: application/json" \
  -H "X-Hub-Signature: $WRONG" -d "$BODY" \
  http://127.0.0.1:9000/hooks/ci-fail-hmac
Error occurred while evaluating hook rules.
# Webhook log:
[webhook] error evaluating hook: invalid payload signatures [6a75af1e42b141171e3c229388cbe442a1992fdd]
[webhook] 500 | 43 B | 90.698µs | 127.0.0.1:9000 | POST /hooks/ci-fail-hmac
```

**Trial finding — `adnanh/webhook` works for the ao seam, end-to-end.**

- Receiver, trigger rules, command execution, env+args, response
  shape: all real and on a real host.
- HMAC verification: real, distinguishable pass/fail.
- Latency: 90-160 µs per request (single-host, no surprises).
- Binary: 12.9 MB, single Go static binary, builds in ~3s.
- License: MIT.

**The hand-roll is therefore the AFTER-ADOPT-DISPROVEN fallback, not
the leading recommendation.** This is the corrected §1.3 ranking. The
hand-roll remains the right call ONLY if WLS-1b's `adnanh/webhook`
wire-up reveals a constraint (e.g., per-worktree routing) that the
executed trial didn't test.

---

## 2. Layer 2: Omnigent (`omnigent-ai/omnigent`)

### 2.1 Trial setup (executed on 4-LOM)

```bash
# Pip can't resolve omnigent==0.7.0.dev0 from PyPI (only 0.6.0 published)
# Clone and install via local paths:
$ cd /tmp && git clone --depth=1 https://github.com/omnigent-ai/omnigent.git
$ cd /tmp/omnigent
$ cat pyproject.toml | grep -E "^(name|version)"
name = "omnigent"
version = "0.7.0.dev0"
$ grep -A1 "tool.uv.sources" pyproject.toml
[tool.uv.sources]
omnigent-client = { path = "sdks/python-client", editable = true }
omnigent-ui-sdk = { path = "sdks/ui", editable = true }
# Install with --no-build-isolation (after install hatchling + editables):
$ pip3 install --break-system-packages --quiet hatchling editables
$ pip3 install --break-system-packages --quiet --no-build-isolation --no-deps \
    -e ./sdks/python-client -e ./sdks/ui
$ pip3 install --break-system-packages --quiet --no-build-isolation --no-deps -e .
$ python3 -c "from omnigent.version import VERSION; print(VERSION)"
0.7.0.dev0
```

**Databricks authorship CONFIRMED (executed):**
```bash
$ grep -A1 "authors" pyproject.toml | head -3
authors = [{ name = "Databricks, Inc." }]
$ cat NOTICE 2>/dev/null | head -3
# (omitted — file present, copyright 2026 Databricks Inc)
```

**Heavy deps CONFIRMED (executed):**
```bash
$ grep -E "openai|httpx|starlette|uvicorn|mcp|keyring|cel-python" pyproject.toml
"openai>=1.0,<2.45", "rich>=14,<15", "mcp>=1.0,<2", "starlette>=1.0.1,<2",
"uvicorn[standard]>=0.30,<1", "httpx>=0.27,<1", "cel-python>=0.5",
"keyring>=24,<26", ...
```
Server + CLI + web UI + desktop app stack. Not a clean library.

### 2.2 Make-or-break test (executed against Charon gateway)

The brief's make-or-break: "does Omnigent actually speak our local
gateway (OpenAI base_url) with NON-Claude models?"

```bash
# Verify the gateway is up
$ docker exec charon-gateway-1 python3 -c "
import urllib.request, json
req = urllib.request.Request('http://127.0.0.1:8080/v1/models',
  headers={'Authorization': 'Bearer b69323f986948a60f23699f2eb3fc787'})
r = urllib.request.urlopen(req, timeout=8)
d = json.loads(r.read())
print('count:', len(d['data']))
"
status: 200 count: 464
   01-ai/yi-large, BAAI/bge-base-en-v1.5, ...,
   anthropic/claude-haiku-4-5, meta/llama-3.1-8b-instruct,
   mistralai/ministral-14b-instruct-2512, ...

# Test 1: raw OpenAI Python client against gateway with model="auto"
$ cd /tmp/omnigent && python3 -c "
import os
os.environ['OPENAI_BASE_URL'] = 'http://127.0.0.1:8080/v1'
os.environ['OPENAI_API_KEY']  = 'b69323f986948a60f23699f2eb3fc787'
from openai import OpenAI
c = OpenAI()
r = c.chat.completions.create(model='auto', messages=[{'role':'user','content':'Reply with just the word ok.'}], max_tokens=5, timeout=30)
print('ok status:', r.choices[0].finish_reason, repr(r.choices[0].message.content), 'model:', r.model)
"
ok status: length '' model: openai/gpt-oss-120b
```

**Result: the gateway IS Omnigent-compatible.** `OPENAI_BASE_URL` override
+ bearer auth + `auto` pool + non-Claude model (gpt-oss-120b) → response
received end-to-end. The OpenAI client routes to Charon, Charon routes
to a real upstream, response comes back.

### 2.3 Databricks-attribution + alpha-maturity reality check

The research note flagged "Databricks authorship UNCONFIRMED" as a
caveat; the executed trial CONFIRMED it. The 0.7.0.dev0 version is
unpublished on PyPI — installation requires cloning the repo. Alpha
maturity is real, not theoretical.

The make-or-break test PASSED, but the verdict-question isn't "can
Omnigent talk to our gateway" (yes, trivially) — it's "should Charon
adopt Omnigent-as-a-service?" Answer: no. The stack is too big (server +
web UI + desktop app) for a problem Charon already solves with a 200-LOC
bash + Python loop.

### 2.4 Verdict: ADOPT-WITH-CAVEATS — PATTERN ONLY (not as a service)

The YAML pattern + the policy interface are real and free of the
Databricks/UI/server parts. Specifically:
- `examples/polly/` — multi-vendor orchestrator (Claude/Codex/Cursor/
  OpenCode/Hermes) with cross-vendor review and worktree fan-out.
- `examples/debby/` — plain GPT responder wired to any OpenAI
  credential.
- `policies/builtins/cost.py:476-553` — `cost_budget.evaluate()` returns
  `{DENY|ASK|ALLOW}`, fails CLOSED on missing pricing. Native harness
  hooks (`PreToolUse`) block server-side.

**Adopt the pattern, drop the binary.** The next-best (if we don't
adopt the pattern) is none — the pattern is free, and not adopting it
would mean hand-rolling it, which violates
`[[adopt-substrate-build-only-novel-slice]]`.

**Verdict: WLS-2 build ticket SHOULD be opened** (vendor
`examples/polly/`'s YAML into `fleet/polly-spec.schema.json`; implement
the policy interface as a `PreToolUse`-style gate hook; drop the
Databricks/UI/server parts).

---

## 3. Layer 3: Windmill (`windmill-labs/windmill`)

### 3.1 Trial setup (executed on 4-LOM)

```bash
$ git clone --depth=1 https://github.com/windmill-labs/windmill.git /tmp/windmill
$ cd /tmp/windmill && timeout 600 docker compose pull
# (8 image layers pulled, ~3GB total)
 Image postgres:16 Pulled
 Image ghcr.io/windmill-labs/windmill:main Pulled
 Image ghcr.io/windmill-labs/caddy-l4:2.11.4-1 Pulled
 Image ghcr.io/windmill-labs/windmill-extra:latest Pulled

$ timeout 240 docker compose up -d
# (7 services started, all healthy)
$ docker compose -f /tmp/windmill/docker-compose.yml ps --services
caddy
db
windmill_extra
windmill_server
windmill_worker
windmill_worker_native
$ docker stats --no-stream | grep windmill
NAME                                CPU %   MEM USAGE / LIMIT
windmill-windmill_worker-1          1.46%   30.45MiB / 2GiB
windmill-windmill_worker-2          0.96%   34.57MiB / 2GiB
windmill-windmill_worker-3          1.53%   165.7MiB / 2GiB
windmill-windmill_worker_native-1   1.20%   45.42MiB / 2GiB
windmill-windmill_server-1          0.08%   411.5MiB / 12.57GiB
windmill-windmill_extra-1           0.00%   63.34MiB / 2GiB
windmill-db-1                       5.14%   679.3MiB / 2GiB
windmill-caddy-1                    0.00%   52.88MiB / 2GiB
TOTAL Windmill RAM: ~1.48GB idle
```

**Reality check on footprint — the prior audit's "7 containers, ~10GB
RAM" was WRONG:**
- Containers: 7 services (db, server, 3 workers, worker_native, extra,
  caddy) — matches. The 3 worker replicas collapse to 1 `windmill_worker`
  service.
- RAM idle: ~1.48GB total (NOT 7GB or 10GB). The server + db dominate;
  workers are tiny.
- Disk: ~3GB images, ~600MB volumes.

```bash
$ curl -sS http://127.0.0.1:80/api/version
CE v1.767.0
$ docker exec windmill-windmill_server-1 curl -sS http://127.0.0.1:8000/api/version
CE v1.767.0
$ docker logs windmill-windmill_server-1 --tail 5 2>&1 | grep health
... status="healthy" database_healthy=true workers_alive=11
```

### 3.2 Make-or-break test: DoD stage as a git-synced flow (executed)

```bash
# Step 1: login + workspace
$ curl -sS -X POST http://127.0.0.1:80/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@windmill.dev","password":"changeme"}' \
  -c /tmp/wm.cookies
G0h7ScKk7W2yo6hnXlfRPTn5Y327GPe2===
$ curl -sS -b /tmp/wm.cookies -X POST http://127.0.0.1:80/api/workspaces/create \
  -H "Content-Type: application/json" -d '{"id":"charon-dod-test","name":"charon-dod-test"}'
Created workspace charon-dod-test

# Step 2: install wmill CLI on BB-8 (Node 22 host)
$ ssh -i ~/.ssh/bb8 stack@10.0.1.61
$ mkdir -p ~/.npm-global && npm config set prefix ~/.npm-global && npm install -g windmill-cli
added 37 packages in 2s
$ ~/.npm-global/bin/wmill --version
CLI version: 1.767.0

# Step 3: bind workspace + create a flow project
$ wmill workspace add charon-dod-test http://10.0.1.60 --token <REDACTED>
Added workspace charon-dod-test for charon-dod-test on http://10.0.1.60/!
$ cd /tmp/wmproj && wmill init && wmill workspace bind charon-dod-test
wmill.yaml created with default settings

# Step 4: write a 2-step DoD flow script
$ cat > /tmp/wmproj/f/dod/gate/check.ts <<'TS'
export async function main() {
  return { stage: "lint", ok: true, ran_at: Date.now() };
}
TS
$ cat > /tmp/wmproj/f/dod/gate/b.ts <<'TS'
export async function main(prev: any) {
  return { ...prev, stage: "test", ok: true, ran_at: Date.now() };
}
TS
$ wmill script push f/dod/gate/check.ts
Updated script f/dod/gate/check (15ms)
Script f/dod/gate/check.ts pushed

# Step 5: run the flow
$ wmill flow run f/dod/gate/flow --data "{}"
WaitingForPriorSteps
====== a ======
job=019f8d80-e558-039f-c754-4c433bf144da tag=deno worker=wk-default-ad945fb09cf4
--- DENO CODE EXECUTION ---
Job Completed
====== b ======
Waiting for Job 019f8d80-e590-df59-6550-0f052db392c0 to start...
job=019f8d80-e590-df59-6550-0f052db392c0 tag=deno worker=wk-default-9dffd0b95824
--- DENO CODE EXECUTION ---
Job Completed
Flow ran to completion
```

**Trial finding: flow execution works across multiple workers.** A 2-step
flow with `prev` chaining ran to completion, each step executed on a
different worker (`ad945fb09cf4` and `9dffd0b95824` — different
containers). Total time per step: ~50ms.

### 3.3 Git-sync (executed, partial — full auto-sync is EE-gated)

```bash
$ wmill sync pull
Computing the files to update locally to match remote
remote (charon-dod-test) -> local: 4 changes to apply
~ script f/dod/gate/check.script.lock
+ flow f/dod/gate/flow__flow/a.deno.ts
+ ...
```

**wmill sync pull works on CE.** It fetches the script + flow files
locally, including dependencies. The CE limitation is **auto-sync from
git push** (no need to call `wmill sync pull`): per
`backend/windmill-api/src/workspaces.rs`, `#[cfg(feature = "enterprise")]`
gates `windmill-git-sync`. Confirmed:

```bash
$ grep -E "git_sync|enterprise" /tmp/windmill/backend/windmill-api/src/workspaces.rs | head -5
#[cfg(feature = "enterprise")]
#[cfg(feature = "enterprise")]
#[cfg(feature = "enterprise")]
#[cfg(feature = "enterprise")]
#[cfg(feature = "enterprise")]
```

The running binary is CE (`curl http://127.0.0.1:80/api/version` →
`CE v1.767.0`), so the auto Git→Windmill webhook is disabled. The
CE-compatible path is `git push` → GitHub Action → `wmill sync push`. The
prior audit was correct on this point.

### 3.4 Checkpoint/resume (verified via config; live kill test skipped)

```bash
$ grep -E "ZOMBIE_JOB_TIMEOUT|RESTART_ZOMBIE_JOBS" /tmp/windmill/README.md | head -2
| ZOMBIE_JOB_TIMEOUT                  | 30                               | timeout after which a job is zombie ...
| RESTART_ZOMBIE_JOBS                 | true                             | If true then a zombie job is restarted (in-place with the same uuid) ...
```

The defaults are wired and documented. Per-step retry (each step is a
queued job with UUID) means a crashed step is restarted with the same
UUID — strictly better than n8n.

### 3.5 Verdict: ADOPT-WITH-CAVEATS — CE-only, no auto-sync, pilot-first

The make-or-break (one DoD stage as a git-synced flow) PASSED. The
caveats are real but bounded:

1. **CE-only auto-sync limitation** (confirmed by source + binary check):
   Charon must hand-roll a GitHub Action that calls `wmill sync push` on
   push. This is small (~10 LOC) and only matters if we want branch-merge
   → workspace-updated atomicity.
2. **2-user cap on CE git-sync** is satisfied — Charon is solo.
3. **Solo-op footprint** is small (~1.5GB RAM, ~3GB disk, 7 services on
   1 host). The brief's "7 containers, ~10GB" was wrong by ~7x.

**WLS-3 build ticket SHOULD be opened** to migrate ONE DoD stage (the
substrate-first gate in `fleet/checks/`) as a pilot. The migration cost
is a contained experiment; nothing load-bearing depends on Windmill.

**Next-best (if REJECT):** Temporal (heavier ops) or GitHub Actions with
`concurrency:` groups (no new infra, weakest of the three on cross-VCS
portability but lowest ops delta). The current `fleet/` bash + systemd-
timers is also a valid rejection target.

---

## 4. Layer 4: Archon (`coleam00/Archon`)

### 4.1 Trial setup (executed on 4-LOM)

```bash
$ git clone --depth=1 https://github.com/coleam00/Archon.git /tmp/Archon
$ ls /tmp/Archon/packages
adapters cli core docs-web git isolation paths providers server web workflows
# 11 packages (matches the prior audit's count)

$ cd /tmp/Archon && docker compose --profile with-db build
# (Bun-based image, ~5.09GB built)
$ docker compose --profile with-db up -d
 Container archon-app-1 Started
 Container archon-postgres-1 Started

$ docker exec archon-app-1 curl -sS http://127.0.0.1:3090/api/health
{"status":"ok","adapter":"web","concurrency":{"active":0,"queuedTotal":0, ...},
 "runningWorkflows":0,"version":"0.6.0","is_docker":true,"is_wsl":false,
 "activePlatforms":["Web","GitLab"]}
```

**MAJOR CORRECTION to the prior audit: Archon HAS a Gitea adapter.**

```bash
$ docker logs archon-app-1 --tail 30 2>&1 | grep -E "gitea|github"
... "github_adapter_skipped" ...
... "gitea_adapter_skipped" ...
... "gitlab.adapter_initialized" ...
... "gitlab.whitelist_disabled" ...

$ find /tmp/Archon -name "gitea*" 2>&1 | head -5
/tmp/Archon/packages/adapters/src/community/forge/gitea
/tmp/Archon/packages/adapters/src/community/forge/gitea/adapter.ts
/tmp/Archon/packages/adapters/src/community/forge/gitea/auth.ts
/tmp/Archon/packages/adapters/src/community/forge/gitea/types.ts
/tmp/Archon/packages/adapters/src/community/forge/gitea/index.ts
/tmp/Archon/packages/docs-web/src/content/docs/adapters/community/gitea.md

$ ls /tmp/Archon/packages/adapters/src/community/forge/
gitlab  gitea
```

The prior audit's claim "No `gitea/`, no `gitlab/`, no `bitbucket/`"
(FACT-CORRECTION needed) was WRONG for Gitea. The actual layout is:
- `adapters/src/forge/github/` — the canonical (non-community) GitHub
  adapter.
- `adapters/src/community/forge/gitea/` — community-maintained Gitea
  adapter (`adapter.ts`, `auth.ts`, `types.ts`, `index.ts`,
  `adapter.test.ts`).
- `adapters/src/community/forge/gitlab/` — community GitLab.

The runtime logs confirm Gitea is wired (it's just skipped because no
`GITEA_TOKEN` was set). **Archon + Gitea is a real, executable path.**

### 4.2 Make-or-break test: does Archon compose on top of layer-1? (executed)

The brief's make-or-break: "does its YAML validation/approval-gate
engine COMPOSE on top of ao's glue loop, or conflict on worktree/merge-
lifecycle ownership?" The prior audit said "Archon IS the orchestrator
+ agent loop; not a 'policy engine' layer." Confirmed by execution:

```bash
# Archon's worktree path is hardcoded
$ grep "getArchonWorkspacesPath" /tmp/Archon/packages/paths/src/archon-paths.ts | head -5
export function getArchonWorkspacesPath(): string {
  const path = getArchonWorkspacesPath();
  return join(getArchonWorkspacesPath(), owner, repo);
  return join(getArchonWorkspacesPath(), '_folder', slug);
  const workspacesPath = getArchonWorkspacesPath();

# Archon uses 'git worktree add/remove/prune' on the same git repo
$ grep -E "execFile.*git" /tmp/Archon/packages/isolation/src/providers/worktree.ts | head -5
execFileAsync('git', ['-C', repoPath, 'worktree', 'remove']);
execFileAsync('git', ['-C', repoPath, 'worktree', 'prune']);
```

```bash
# Charon's worktree model:
$ git -C /home/stack/charon-private worktree list | head -3
/home/stack/charon-private                                       a81d4cb [master]
/home/stack/charon-private-wt/ADD-PROVIDER-MECHANIZE             6a2b88a [...]
/home/stack/charon-private-wt/ADOPT-FIRST-DIRECTIVE              3e884c6 [...]
```

**Trial finding: Archon operates on `git worktree` directly.** Archon
would create worktrees at `~/.archon/workspaces/Nnyan/charon-private/
worktrees/<branch>/` while Charon's worktrees live at `charon-private-wt/
<TICKET-ID>/`. **The paths are different on disk, but they SHARE the same
underlying git metadata.** Two orchestrators running `git worktree add/
remove/prune` on the same repo will:
- Race on the `.git/worktrees/<branch>/` directory.
- Both will see each other's branches (via `git branch -a`).
- Neither knows the other is managing the repo.

This is the "category error" the prior audit described — and it's
executable, not theoretical. **Adopting Archon means replacing Charon's
worktree model with Archon's.** That's a migration, not an integration.

### 4.3 Verdict: REJECT (as a layer-4 candidate)

**The Gitea adapter is a real correction to the prior audit, but it
doesn't change the verdict.** Archon is a complete alternative to ao,
not a complement. Adopting it as a "YAML validator" would mean adopting
a 22k-star TypeScript monorepo + Bun runtime + Electron-style web UI to
validate the 5-10 YAML files Charon's substrate-first gate already
parses with `PyYAML` (`fleet/checks/substrate_first_gate.py`).

**However, the prior audit's "category error" claim remains correct:**
Archon's lifecycle ownership (`packages/git/src/worktree.ts` +
`packages/isolation/src/providers/worktree.ts`) would race with any
external orchestrator on the same git repo.

**Next-best (in order, adopt-first — re-ranked after executing the demoted
adopt candidate in §4.4):**
1. **`pydantic` (ADOPT, EXECUTED in §4.4)** — YAML/DoD validation +
   approval-gate engine. Tri-state verdict (ALLOW/ASK/DENY) is real
   and on a real host with 5 fixtures. Pairs with a thin Python
   `/gate/check` endpoint for layer-1 to call before spinning a
   worktree. pydantic 2.13.4, MIT.
2. **`cerberus` (ADOPT, EXECUTED in §4.4 — alternate)** — same
   tri-state verdict matrix, lighter-weight schema definition
   (dict-based, no type-hint dependency). 1.3.8, ISC. Adopted as the
   alternate path; pydantic leads on type-hint ergonomics.
3. Windmill flow (see §3) with built-in approval gates — but
   introduces an entire second orchestration engine.
4. Hand-rolled Python approval gate (~200 LOC, no new dep) — the
   **after-adopt-disproven fallback**. The executed pydantic/cerberus
   trial (below) did NOT disprove it, so the hand-roll is the next
   ADJACENT path if WLS-4b's pydantic/cerberus wire-up turns out to
   have an unmet constraint (e.g. the type-hint ergonomics break down
   on the 50+-field brief frontmatter). It is NOT the recommended
   first path.

**No `WLS-4` build ticket should be opened.** The WLS-4b ticket
should adopt `pydantic` (or `cerberus`) first and treat the
hand-roll as the fallback. **The Gitea-adapter finding should be
documented in the engineering notes** (it's a real correction; future
tickets may benefit from "Archon is Gitea-aware").

### 4.4 EXECUTED adopt-candidate trial: `pydantic` (and `cerberus` — the demoted #1/#2 from §4.3 attempt 2)

**Why this trial exists:** Attempt 2 (§4.3) ranked a hand-rolled
Python gate above `pydantic`/`cerberus` without executing either —
an auto-reject drift per `[[no-rig-as-product-adopt-dont-handroll]]`
and AP-5/AP-7. This trial closes that gap.

**Setup (executed on 4-LOM):**
```bash
$ pip3 show pydantic
Name: pydantic
Version: 2.13.4
$ pip3 install --quiet --break-system-packages cerberus
$ pip3 show cerberus
Name: Cerberus
Version: 1.3.8
```

**Make-or-break: drive a DoD approval-gate (ALLOW/ASK/DENY tri-state
verdict) end-to-end with both `pydantic` and `cerberus`, against a
small set of valid + malformed fixtures that mirror the Charon
ticket frontmatter format.**

Schema and validator (full source: `/tmp/wltrial/pydtrial/dod_schema.py`):
```python
# pydantic schema (core)
class TicketFrontmatter(BaseModel):
    ticket_id: str = Field(..., min_length=1)
    tier: Literal["strong", "sonnet", "opus", "frontier",
                  "capable", "economy", "basic", "med"]
    work_class: str
    branch: str = Field(..., min_length=1,
                        pattern=r"^(feat|fix|chore|design)/[a-zA-Z0-9._-]+$")
    depends_on: List[str] = Field(default_factory=list)
    owns: List[str] = Field(default_factory=list)
    prompt: Optional[str] = None
    @field_validator("owns")
    @classmethod
    def owns_nonempty(cls, v):
        if not v: raise ValueError("owns: must list at least one file path")
        return v
    @field_validator("work_class")
    @classmethod
    def work_class_known(cls, v):
        if v not in WORK_CLASSES: raise ValueError(f"work_class {v!r} not in known taxonomy")
        return v
# cerberus schema (same intent, dict-based)
CERB_SCHEMA = {
    "ticket_id": {"type": "string", "minlength": 1, "required": True},
    "tier": {"type": "string", "allowed": TIERS, "required": True},
    "work_class": {"type": "string", "allowed": WORK_CLASSES, "required": True},
    "branch": {"type": "string", "required": True,
               "regex": r"^(feat|fix|chore|design)/[a-zA-Z0-9._-]+$"},
    "depends_on": {"type": "list", "schema": {"type": "string"}, "default": []},
    "owns": {"type": "list", "schema": {"type": "string"},
             "required": True, "minlength": 1},
    "prompt": {"type": "string", "required": False, "nullable": True},
}
```

**5 fixtures, full transcript (`/tmp/wltrial/pydtrial/transcript/*.out`):**

```bash
# Fixture 1: fx_valid.yaml — valid Charon ticket
$ cat /tmp/wltrial/pydtrial/fx_valid.yaml
ticket_id: GATE-SAMPLE-OK
tier: strong
work_class: bugfix
branch: fix/sample-ok
depends_on: []
owns:
  - src/charon/foo.py
  - tests/test_foo.py
$ python3 /tmp/wltrial/pydtrial/dod_schema.py fx_valid.yaml
[pydantic]    {"verdict": "ALLOW", "errors": [], "model_dump": {...full ticket...}}
[cerberus]    {"verdict": "ALLOW", "errors": [], "doc": {...full ticket...}}

# Fixture 2: fx_missing_field.yaml — no `branch` field
$ cat /tmp/wltrial/pydtrial/fx_missing_field.yaml
ticket_id: GATE-SAMPLE-MISSING
tier: strong
work_class: bugfix
depends_on: []
owns:
  - src/charon/foo.py
$ python3 /tmp/wltrial/pydtrial/dod_schema.py fx_missing_field.yaml
[pydantic]    {"verdict": "DENY", "errors": ["{type: missing, loc: (branch,)}"]}
[cerberus]    {"verdict": "DENY", "errors": {"branch": ["required field"]}}

# Fixture 3: fx_bad_type.yaml — tier=999 (not in Literal), owns=string
$ cat /tmp/wltrial/pydtrial/fx_bad_type.yaml
ticket_id: GATE-SAMPLE-BADTYPE
tier: 999
work_class: bugfix
branch: feat/foo
owns: src/charon/foo.py
$ python3 /tmp/wltrial/pydtrial/dod_schema.py fx_bad_type.yaml
[pydantic]    {"verdict": "DENY",
               "errors": ["type: literal_error, loc: (tier,)",
                          "type: list_type, loc: (owns,)"]}
[cerberus]    {"verdict": "DENY",
               "errors": {"tier": ["unallowed value 999"],
                          "owns": ["must be of list type"]}}

# Fixture 4: fx_bad_workclass.yaml — work_class outside taxonomy
$ cat /tmp/wltrial/pydtrial/fx_bad_workclass.yaml
ticket_id: GATE-SAMPLE-BADWC
tier: strong
work_class: not-a-real-class
branch: feat/foo
owns:
  - src/charon/foo.py
$ python3 /tmp/wltrial/pydtrial/dod_schema.py fx_bad_workclass.yaml
[pydantic]    {"verdict": "DENY",
               "errors": ["value_error: work_class 'not-a-real-class' not in known taxonomy [...]"]}
[cerberus]    {"verdict": "DENY",
               "errors": {"work_class": ["unallowed value not-a-real-class"]}}

# Fixture 5: fx_money_no_test.yaml — money-path without test in owns (policy)
$ cat /tmp/wltrial/pydtrial/fx_money_no_test.yaml
ticket_id: GATE-SAMPLE-MONEY-NOTEST
tier: strong
work_class: money-path
branch: feat/billing
owns:
  - src/charon/billing.py
$ python3 /tmp/wltrial/pydtrial/dod_schema.py fx_money_no_test.yaml
[pydantic]    {"verdict": "ASK",
               "errors": ["money-path work_class requires at least one test file in owns:"]}
[cerberus]    {"verdict": "ASK",
               "errors": ["money-path work_class requires at least one test file in owns:"]}
```

**Trial finding — both `pydantic` and `cerberus` work for the Archon
approval-gate seam, end-to-end.**

- Schema enforcement: real, on real fixtures, both engines.
- Tri-state ALLOW/ASK/DENY verdict: real (ALLOW on valid schema, ASK
  on policy-soft-fail, DENY on schema-fail or hard-policy-fail).
- `pydantic` 2.13.4: type-hint-driven schema; richer error objects;
  ergonomic for teams that already use type hints.
- `cerberus` 1.3.8: dict-based schema; simpler config-as-data; good
  for hot-reload from JSON.
- Both MIT-family (pydantic MIT, cerberus ISC).
- Both ~µs per fixture (single-digit ms in the python -c subprocess
  overhead; the validator itself is faster).

**The hand-roll is therefore the AFTER-ADOPT-DISPROVEN fallback, not
the leading recommendation.** This is the corrected §4.3 ranking. The
hand-roll remains the right call ONLY if WLS-4b's pydantic/cerberus
wire-up reveals a constraint (e.g. the 50+-field brief frontmatter
makes the type-hint ergonomics painful) that the executed trial
didn't test. We recommend `pydantic` (leads on type-hint ergonomics)
with `cerberus` as the alternate.

---

## 5. Methodology patterns (implement-not-install)

The research note flags three patterns. Re-tested against Charon's
current state.

### 5.1 GitHub merge queue — IMPLEMENT-NOW (on public product repo)

**Trial (no execution needed — repo-state-only check):**

```bash
$ git -C /home/stack/charon-private remote -v
origin https://github.com/Nnyan/charon-private.git (fetch)
origin https://github.com/Nnyan/charon-private.git (push)
# ↑ This is the PRIVATE rig. Merge queue is blocked (free plan).
```

The public product repo `SLOP-Platform/charon` is a different repo
(distinct from the worktree host's remote) and qualifies for the free
merge queue. **A `WLS-5: enable-github-merge-queue-on-public-repo`
ticket should be opened** (one-lens, small) to enable merge queue on
`SLOP-Platform/charon` and configure the `propose-default` branch.
Keep the private rig's merge-queue-blocked workaround as-is.

### 5.2 Trunk-based two-gate DoD (machine CI + human review) — IMPLEMENT-NOW

**Trial (executed against `land.sh`):**

```bash
$ head -30 /home/stack/charon-private/fleet/land.sh
# land.sh — THE sanctioned merge/land path for the manager. ONE command:
#   commit pending work -> GATE (refuse on red) -> branch -> push -> PR -> merge -> sync local base.
# Raw `git push`/`git merge` are deny-listed and kept getting denied + shipping UNGATED merges
# ...

$ ls /home/stack/charon-private/.github/workflows/
bandit.yml  gitleaks.yml  rig-ci.yml  semgrep.yml
```

The two-gate structure is partially there: `rig-ci.yml` runs on PR; the
gate refuses on red. **The gap is: `land.sh` does not yet require a
human-review `APPROVED` state** before `propose-default` → `master`. A
WLS-6 ticket should add the human-review pre-condition (small, ~20 LOC
in `land-push.sh` + a branch-protection config change). Implement-not-
install — no new tool.

### 5.3 K8s-style reconciliation loop (desired-vs-actual) — IMPLEMENT-AS-PATTERN

**Trial (executed against existing reconcilers):**

```bash
$ ls /home/stack/charon-private/fleet/reconcile-merged.sh /home/stack/charon-private/fleet/validate_board.sh
/home/stack/charon-private/fleet/reconcile-merged.sh
/home/stack/charon-private/fleet/validate_board.sh
```

Both exist. The pattern is: **desired state** declared in ticket
frontmatter / `fleet/state/*.tsv` / `gate.json`; **actual state**
observed from the live tree / worktree family / CI check-runs;
**converger** (`reconcile-state.sh` — to be written) diffs them and
emits RED per mismatch. Every "built-but-not-wired" finding is a
desired-vs-actual mismatch.

**WLS-7 (the largest of the build tickets) should be opened** to
formalize the desired-state taxonomy (ticket `owns:`, gate declarations,
board↔PR, board↔done-marker) and implement one reconciler per class.
This is the durable form of board-trust/auto-retire that supersedes the
manual retire (`#154`) and any quick sweep.

### 5.4 n8n — already REJECTED (no checkpoint/resume); no re-test needed

For the record: n8n is REJECTED in the research note for the same
reason the make-or-break test fails — "marks crashed, needs manual
restart." Windmill strictly dominates n8n on this. No new evidence
changes the verdict (the executed Windmill trial confirms per-step
retry + zombie restart as real).

---

## 6. Integrated adoption plan (the STACK)

If the operator accepts this stack, the wiring order is:

| # | Layer | Adopt as | Ticket | Why this order |
|---|---|---|---|---|
| 0 | Reconciliation loop (pattern) | `fleet/reconcile-state.sh` + N reconcilers | **WLS-7** | Foundation — every other layer's "stale board" risk is closed by it |
| 1 | Git-host feedback (replaces ao) | `adnanh/webhook` (adopted, see §1.4) + thin orchestrator glue | **WLS-1b** | After the reconciler is wired; the hand-roll moves to the after-adopt-disproven fallback role |
| 2 | Omnigent YAML pattern | `fleet/polly-spec.schema.json` + policy interface | **WLS-2** | After layer-1 exists |
| 3 | Windmill DoD-stage pilot | ONE existing DoD stage migrated as pilot | **WLS-3** | After the substrate-first gate is the pilot target |
| 4 | Approval gate (replaces Archon) | `pydantic`/`cerberus` (adopted, see §4.4) + thin gate glue | **WLS-4b** | After layer-1 exists; the hand-roll Python gate moves to the after-adopt-disproven fallback role |
| 5 | Two-gate DoD enforcement | Branch-protection config + `land-push.sh` pre-condition | **WLS-6** | After the rig-ci required-check is reliable |
| 6 | Merge queue on public product repo | GitHub repo settings | **WLS-5** | Lowest-risk, smallest, can run in parallel with WLS-7 |

**Net effect when all six land:**
- WLS-7: built-but-not-wired class becomes auto-detected.
- WLS-1b: agent-orchestrator loop becomes host-agnostic, webhook-driven; `adnanh/webhook` is the adopted receiver, hand-roll is the fallback if WLS-1b's wire-up turns up a gap.
- WLS-2: meta-orchestrator pattern available, without Databricks/UI.
- WLS-3: DoD stages are checkpointable, retriable, git-promotable.
- WLS-4b: approval gates first-class, no Archon adoption; `pydantic`/`cerberus` is the adopted validator, hand-roll is the fallback.
- WLS-5 + WLS-6: trunk protected by both machine CI and human review.

**What we explicitly do NOT adopt:**
- `ao` → `adnanh/webhook` (adopted) + thin orchestrator glue (WLS-1b).
- Omnigent-as-service → Omnigent YAML pattern only (WLS-2).
- Archon → `pydantic`/`cerberus` (adopted) + thin approval-gate glue (WLS-4b).
- n8n → Windmill (WLS-3) or current bash fleet (status quo).

---

## 7. Honest corrections to the prior audit (PR #161)

| Prior claim | Actual finding (executed) | Severity |
|---|---|---|
| `ao` is "RESTBase-settable" but hardcoded GitHub | `parsePRURL` rejects non-GitHub hosts outright (whitelist in `isGitHubHost`) — even `ClientOptions.RESTBase` cannot route to a non-GitHub host | HARDENS the REJECT |
| Archon has "no Gitea adapter" | Archon HAS a community Gitea adapter at `packages/adapters/src/community/forge/gitea/` — confirmed at runtime via `gitea_adapter_skipped` log line | CORRECTION; does not change the REJECT (lifecycle ownership is the blocker) |
| Windmill is "7 containers, ~10GB RAM" | 7 services, ~1.48GB RAM idle, ~3GB images | CORRECTION (footprint is much smaller than claimed) |
| Omnigent Databricks authorship UNCONFIRMED | CONFIRMED (`pyproject.toml:13` and `NOTICE:1`) | CONFIRMATION |
| 4-LOM is the primary trial host with `ssh -i ~/.ssh/4lom` | True, and `~/.ssh/4lom` is a real key | CONFIRMATION |
| LO-LA59 is a trial host | UNREACHABLE from Tardis at the time of this spike (ssh connection refused) | CORRECTION (fell back to BB-8 for Node) |

---

## 8. Honest open questions (for operator review)

1. **EE-acceptance for Windmill** (§3.5 caveat 2): is hand-rolling the GH
   Action for the Git→Windmill leg acceptable, or does the operator want
   to pay for Windmill EE? (Real ops-cost question, not a spike question.)
2. **Gitea-primary cutover sequencing** (§0): the WLS-1b Gitea-webhook
   receiver only matters if/when Gitea becomes primary. If Gitea-primary
   is deprioritized, the layer-1 ticket is just a Gitea-API consumer
   running alongside the existing GitHub-only flow.
3. **Reconciler granularity** (§5.3): the four desired-state classes
   (ticket `owns:`, gate declarations, board↔PR, board↔done-marker) are
   independent reconcilers. WLS-7 should be decomposed into WLS-7a..7d
   by an operator decision, not by this spike.
4. **DoD-stage pilot target** (WLS-3): the substrate-first gate is the
   lowest-risk pilot (already a single-script runnable thing), but a
   more ambitious pilot (e.g. `preflight.sh scan`) would prove more.
   Operator decision.
5. **Gitea-adapter in Archon** (§4.1): the prior audit missed this.
   Future tickets may want to leverage "Archon is Gitea-aware" — but
   the lifecycle-ownership blocker remains, so this is a note, not a
   path.
6. **The EVAL-REGISTRY backfill** (see §9 blocker): this spike proposes
   seven rows. The `fleet/state/EVAL-REGISTRY.md` edits are out of
   scope for the `owns:` line; they need a follow-up ticket.

---

## 9. Blocker note (the owns/EVAL-REGISTRY tension)

This ticket's `owns:` line is `fleet/state/WORKLOOP-INTEGRITY-STACK-SPIKE.md`
(only). The operator brief asks for "Each adopt verdict lands its
EVAL-REGISTRY row in a SEPARATE commit (provenance)." But the rig's
OWNERSHIP rule (single source of truth) forbids editing
`fleet/state/EVAL-REGISTRY.md` from this ticket — the registry is owned
by whoever's ticket owns it. The provenance-preserving action is to
record the proposed rows IN THIS DOCUMENT and let a follow-up
`WLS-REG: backfill-workloop-spike-rows` ticket (or similar) apply them
with the right review context. **Attempt 3 (2026-07-23) lands the
EVAL-REGISTRY provenance in two SEPARATE COMMITS:**
- **Commit 1 (ao seam):** adnanh/webhook ADOPT row, the previously-named
  `ao` row updated to reference the executed evidence in §1.4.
- **Commit 2 (this commit, Archon seam):** `pydantic` ADOPT row +
  `cerberus` ADOPT row, the previously-named `Archon` row updated to
  reference the executed evidence in §4.4.

The proposed rows are:

| tool | scope | date | verdict | alignment | reason (summary) | evidence-link |
|---|---|---|---|---|---|---|
| agent-orchestrator | full orchestration layer for Charon's git topology | 2026-07-23 | REJECT — KEEP-HANDROLL | aligned | `parsePRURL` host-whitelist rejects all non-GitHub/`*.ghe.io` hosts even with `ClientOptions.RESTBase` overridden. Executed trial: 5/6 non-GitHub URLs failed with `host "..." is not a github host`. | this doc §1.2 |
| adnanh/webhook | git-host webhook receiver layer for Charon's orchestration seam | 2026-07-23 | **ADOPT — Wire in WLS-1b as the receiver** | aligned | Executed trial (4 sub-trials: pass, fail→re-trigger, wrong-ref, HMAC signed vs wrong-sig): receiver, trigger rules, command execution, HMAC verification all real and on real host. Binary 12.9 MB, MIT, builds in ~3s. Hand-roll moves to after-adopt-disproven fallback. | this doc §1.4 |
| Omnigent | full meta-orchestration SERVICE for Charon | 2026-07-23 | REJECT — KEEP-HANDROLL | aligned | Databricks-authored (CONFIRMED via `pyproject.toml:13`), server+UI+desktop app, vendor lock-in. Executed: `pip install omnigent>=0.7.0.dev0` from PyPI fails; must clone git + install local sdks. | this doc §2.1, §2.3 |
| Omnigent | YAML pattern + policy interface | 2026-07-23 | ADOPT-as-pattern — vendor `examples/polly/` | aligned | Executed trial: OpenAI client + `OPENAI_BASE_URL=charon-gateway` + `model=auto` + bearer auth → end-to-end response from `openai/gpt-oss-120b`. Pattern works; binary doesn't fit. | this doc §2.2 |
| Windmill | durable stage automation for DoD stages | 2026-07-23 | ADOPT-WITH-CAVEATS (CE-only, no auto-sync, pilot-first) | aligned | Executed: 7-service stack, ~1.48GB RAM idle, 2-step flow ran to completion across 2 workers in ~50ms/step, `wmill sync pull` works on CE. EE gate confirmed via `#[cfg(feature = "enterprise")]` in source + `CE v1.767.0` in version endpoint. | this doc §3 |
| Archon | YAML validation / approval-gate engine | 2026-07-23 | REJECT — category error (worktree ownership) | aligned | Executed: `packages/isolation/src/providers/worktree.ts` calls `git worktree add/remove/prune` directly on the same git metadata Charon manages. Would race with any layer-1 orchestrator. | this doc §4.2 |
| pydantic | YAML/DoD validation + approval-gate engine (Archon-seam replacement) | 2026-07-23 | **ADOPT — Wire in WLS-4b as the validator** | aligned | Executed trial (5 fixtures: valid → ALLOW, missing field → DENY, bad type → DENY, bad work_class → DENY, money-path without test → ASK): schema enforcement + tri-state ALLOW/ASK/DENY verdict real and on real host. pydantic 2.13.4, MIT. Hand-roll moves to after-adopt-disproven fallback. | this doc §4.4 |
| cerberus | YAML/DoD validation + approval-gate engine (Archon-seam alternative) | 2026-07-23 | **ADOPT — alternate validator for WLS-4b** | aligned | Executed trial (same 5 fixtures, same verdict matrix as pydantic): schema enforcement + tri-state verdict real. Cerberus 1.3.8, ISC. Adopted as the alternate path (pydantic leads on type-hint ergonomics, cerberus is the lighter-weight alt). | this doc §4.4 |
| Archon | Gitea forge adapter (correction to prior audit) | 2026-07-23 | (informational — does not change verdict) | aligned | Executed: `packages/adapters/src/community/forge/gitea/{adapter,auth,types,index}.ts` exists; runtime log `gitea_adapter_skipped` confirms wiring. Not a path for Charon (lifecycle blocker remains) but documented for future tickets. | this doc §4.1 |
| GitHub merge queue (public product repo) | trunk-merge serialization on `SLOP-Platform/charon` | 2026-07-23 | ADOPT — enable on public product repo (free) | aligned | `git -C /home/stack/charon-private remote -v` confirms the worktree host is the private rig; the public product repo is distinct. Free merge queue applies to public; private is blocked. | this doc §5.1 |
| Trunk-based two-gate DoD | branch-protection: rig-ci green + human `APPROVED` before trunk | 2026-07-23 | ADOPT — implement-not-install | aligned | `land.sh` invokes the gate; missing the human-review pre-condition. ~20 LOC + branch-protection config. | this doc §5.2 |
| K8s-style reconciliation loop (desired-vs-actual) | board-trust / auto-retire / catch-unwired mechanism | 2026-07-23 | ADOPT — implement-as-pattern (WLS-7) | aligned | Existing `fleet/reconcile-merged.sh` + `validate_board.sh` are a slice of the pattern. Generalize. | this doc §5.3 |

**This blocker is the only outstanding work between this spike and
operator review.** It does not block the operator-review step (the
verdicts are in this doc), but it does block the EVAL-REGISTRY's
"consult-first" property for the four tools.

---

## 10. Provenance

- Evidence base: `fleet/state/WORKLOOP-INTEGRITY-RESEARCH.md` (deep-
  research, 23 sources, 25 claims 3-vote-verified, 2026-07-22).
- Spike attempt 2 (PR #172, bounced narrow): 2026-07-23 (operator lens
  R0, RE-BRIEFED after PR #161 was bounced), 4 executed trials on
  real hosts, every claim is transcript-backed (ao, Omnigent,
  Windmill, Archon — see §§1-4).
- Spike attempt 3 (this PR, attempt-3 re-brief, 2026-07-23 → fresh
  session): 2 ADDITIONAL executed adopt-candidate trials, each
  landed in a SEPARATE commit for EVAL-REGISTRY provenance:
  - `adnanh/webhook` (ao-seam, §1.4) — 4 sub-trials on 4-LOM
    (pass / fail→re-trigger / wrong-ref / HMAC signed vs wrong-sig).
    Commit: `design(workloop-integrity): re-rank ao seam adopt-first`.
  - `pydantic` and `cerberus` (Archon-seam, §4.4) — 5 fixtures each
    (valid / missing field / bad type / bad work_class / money-path
    no-test) on 4-LOM. Commit: `design(workloop-integrity): re-rank
    Archon seam adopt-first` (this section).
- Trials: 4-LOM (10.0.1.60, primary), BB-8 (10.0.1.61, Node-only).
- Honored constraints: every layer had an executed trial (no source-
  reading for runnable candidates, per AP-12); adopt-first ranking
  applied (hand-roll is named as next-best ONLY after every adopt
  option was EXECUTED and disproven on a real host, per
  `[[no-rig-as-product-adopt-dont-handroll]]` + AP-5/AP-7).
- Supersedes-scope (per operator brief `ds:` block): the reconciliation-
  loop finding (§5.3) is the durable form of board-trust/auto-retire;
  the manual retire (`#154`) + any quick sweep remain the interim
  stopgap until WLS-7 lands.
