tier: strong
difficulty: 2
work_class: ci-infra
branch: feat/add-provider-mechanize
repo: charon-private
depends_on:
owns: fleet/add-provider.sh, fleet/tests/test_add_provider.sh
accept: |
  ONE command to add a provider to the live gateway, so no session re-derives the .60/CLI/keys plumbing again
  (operator 2026-07-13 — I burned a turn reverse-engineering it). Facts in memory charon-gateway-config-how-to.
  DO fleet/add-provider.sh <name> <base_url> <local-key-file> [model:upstream ...]:
    1. Back up /data first (docker exec cp to a .bak-<ts>).
    2. Use the CHARON CLI (NOT hand-edited JSON — keys are GPG-managed): `docker exec charon-gateway-1 python3 -m
       charon.cli providers add <name> --base-url <url>` with the key from the LOCAL secrets file, passed so it
       NEVER lands in argv / ps / logs / this transcript (stdin or a scoped env, verified).
    3. `models import <name>` (or add the given model:upstream mappings with cost_rank) + `providers test <name>`.
    4. Restart charon-gateway-1 (docker-gated) + verify the new models appear in GET /v1/models.
  Idempotent, fail-loud on any step. All ssh via `ssh -i ~/.ssh/4lom stack@10.0.1.60`.
  FAIL-ON-REVERT (test): a --dry-run / mocked-ssh path asserts the exact CLI call sequence AND that the key value
  never appears in the emitted commands/logs (grep the transcript). Revert the key-safety -> key leaks into argv
  -> RED.
scope: mechanize provider onboarding — the "link providers" component of MODEL-LIFECYCLE. [[charon-gateway-config-how-to]] [[public-repo-no-personal-info]]
ds: |
  depends_on: none. Component of MODEL-LIFECYCLE. Sonnet/bounded infra script. repo charon-private (rig tool).
note: one-command provider add via the charon CLI; safe key handling; the wrapper that ends the manual reverse-engineering.
