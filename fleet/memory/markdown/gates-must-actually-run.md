---
description: "DIRECTIVE — a \"green\" gate proves nothing unless it actually EXECUTED; verify the gate ran (N checks, correct invocation), not just that CI is green"
metadata: 
name: gates-must-actually-run
node_type: memory
originSessionId: fffc7f6f-75c2-4588-b70e-1d3885da5281
type: feedback
tags: [gate]
last_referenced: 2026-07-13
---
Root cause of the KEYSTONE KS31/KS29 ship-broken (2026-07-12): the KSF CI workflow invoked `ksf gate --repo-root .`, but `--repo-root` is a global arg argparse requires BEFORE the subcommand (`ksf --repo-root . gate`), so the CI step ERRORED on every run since 07-11. The "green build" was never real — the gate never executed. Compounded by two real loopholes: `inert_code` counted test-only refs as reachable (a symbol reachable only from its own test passes), and KS29's `check_registry` gate lived outside `ksf/gates/` + wasn't in the manifest, so GateRunner never discovered it.

**Why:** a gate that isn't executed is indistinguishable from a passing gate if you only look at the CI color. Last session trusted the SUCCESS line over a never-real green — the exact class of [[document-model-self-report-lies]] / [[never-ignore-preexisting-issues]] failure, one level up: not the model lying, the harness silently inert.

**How to apply:** when a build claims green, verify the gate actually RAN — correct invocation, expected number of checks executed, fail-loud on zero-checks. Prefer a meta-gate that asserts every `check_*` is registered in the manifest+firing path, and that CI counts N gates ran. Hardening tickets H1 (inert_code reject test-only-only reachability), H2 (meta-gate: every check_* in manifest), H3 (CI assert N gates ran) capture this; see fleet/state/GATE-MISS-POSTMORTEM.md.
