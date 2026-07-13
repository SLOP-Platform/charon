---
description: "Hard-won 2026-07-03 deploy lessons — the self-hosted-runner gateway's deployed image/config drifted from the tagged source in several ways; what broke and how to avoid it"
metadata: 
name: charon-deploy-drift-lessons
node_type: memory
originSessionId: a8f924d0-22f6-4f2b-ac52-79591b72effd
type: project
tags: [charon, deploy, ops]
last_referenced: 2026-07-13
---
2026-07-03 firefight deploying Charon `v0.2.1` (leak fix) to self-hosted-runner revealed the **deployed image ≠ tagged source** in multiple ways. Lessons for future deploy work:

1. **Config/secrets/state must live on the mounted volume, and the env must point there.** The gateway reads config via `--state-dir`/`CHARON_HOME` but loads **secrets** (provider keys) from `secrets.config_dir()` = `$CHARON_HOME`. The v0.2.1 image left `CHARON_HOME` empty (only `CHARON_STATE_DIR=/work/.charon`, ephemeral), so secrets loaded from the wrong path → **all provider keys `[key MISSING]` → upstream 401 "Missing API key."** Fix: set **`CHARON_HOME=/data` AND `CHARON_STATE_DIR=/data`** (the mounted `charon-config` volume) in the compose. Config on `/data`: `gateway.json, models.json, pools.json, providers.json, secrets.json`. Codified in SR-10 / DECISIONS **D024**.

2. **The deployed image had capabilities the tagged source lacks.** v0.2.0 image = `charon-entrypoint` + CMD `charon gateway :8080`; v0.2.1 image (from hotfix off v0.2.0 tag) = ENTRYPOINT=null + CMD `uvicorn …:8473` (Mode-B default). And v0.2.0 had **`opencode-zen`** as a built-in provider preset; **v0.2.1 source dropped it** (kept `opencode-go` = `.../zen/go/v1`), so the config crash-looped on `unknown provider 'opencode-zen'`. Band-aid: add `base_url: https://opencode.ai/zen/v1` override in `providers.json`. Proper fix: re-add `opencode-zen` as a built-in preset in `providers.py` (ticketed).

3. **The self-hosted-runner `~/charon/docker-compose.yml` is a hand-maintained deploy file that diverged from the repo compose** (single gateway service vs the repo's 2-service). SR-10 makes the repo compose the source of truth (image-only, single-producer, correct env/command); on next deploy, replace self-hosted-runner's hand-file with the SR-10 compose to unify.

4. **`opencode-zen`/`opencode-go` share ONE key** (`OPENCODE_ZEN_KEY`); it's valid for both `.../zen/v1` and `.../zen/go/v1` (200 on `/models`). A 401 is treated as auth → Charon does NOT fail over (assumes bad-key-everywhere).

Meta: this is why [[investigate-and-backup-before-data-loss]] matters, and reinforces the [[product-vs-build-rig-boundary]] north-star of a fresh-install-clean deploy. Deploy access via [[fleet-rig-absolute-path]]/self-hosted-runner. All keys stay in `/data/secrets.json` only (public-repo hygiene: [[public-repo-no-personal-info]]).
