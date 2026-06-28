# WORK-LAND-PR — close the loop (PR behind a flag) + wire the real reviewer

## What shipped
Two parts, one ticket (operator decision 2026-06-27):

**(a) Open a PR behind a flag.** New `charon work --open-pr` (OFF by default,
fail-closed). When armed, each unit whose land verdict is *propose* is published
as a **DRAFT PR**: `land.propose_pr(...)` points a branch (`charon/land/<id>`) at
the unit's blessed tip, pushes it, then `gh pr create --draft` (reusing the
existing `land.open_pr`). When off, the work path is byte-for-byte today's
behavior — read-only, no branch, no push, no PR. **Never auto-merges** (ADR-0010
D5 propose-default); a human/other-agent merge is the only thing that lands
anything. `run_work` gained `open_pr` + a `pr_opener` test seam + `pr_base`/
`pr_repo_slug`; the report carries `open_pr` and a per-unit `pr` field.

**(b) Wire the real reviewer.** The work path now threads
`adapters.review.GatewayReviewer` (the real cross-model, loopback-gateway
reviewer) into the fenced runner — additive to the acceptance checks, never
weakening them. Mirrors how `charon run` constructs+passes a reviewer, but uses
the gateway reviewer (not the demo `MockReviewer`), so it composes with the
merged WORK-GATEWAY-WIRE credential forwarding.

## Key decision — where the reviewer wiring lives (owns mismatch)
The ticket's `owns` lists `coordinator.py` "for threading the reviewer into
CoordinatorRunner", but `CoordinatorRunner` actually lives in
`engine/scheduler.py` (NOT in `owns`). The ticket NOTE explicitly blesses doing
the wiring **entirely in cli.py** if it works out that way — so I did, rather
than editing the unowned scheduler or running release.sh.

`cli._ReviewingRunner` is a `FencedRunner` that drives each unit through the SAME
single fenced `coordinator.run` the default `CoordinatorRunner` uses, but passes
`reviewer=`. `cli.build_work_runner(...)` constructs it with a `GatewayReviewer`.
This duplicates ~25 lines of the scheduler's runner wiring — an acknowledged
cost of the `owns` ceiling. It is **not** a second/unfenced dispatch path: every
unit still goes through `coordinator.run` (the D008 fence choke-point is
preserved). All engine/core imports stay LAZY (inside `__call__`/the builder) so
engine never lands on cli.py's module-load path (boundary guard stays green).

## Honest scope
- At the work default autonomy (L1) `coordinator.run` consults the reviewer only
  at **L2+**; the reviewer is threaded + recorded at every level and BLOCKS at
  L2+. So part (b) makes the gateway reviewer reachable/active for autonomous
  work; it is dead-on-arrival no longer. Tests assert construction+threading
  (the acceptance bar), not L2 blocking.
- In the sandbox/demo path there is no git remote, so `--open-pr`'s push fails
  fast → caught, surfaced in the unit's `note` (`pr not opened: …`), no crash.
  Real `--repo` with a remote opens the PR.

## Gate
`pytest` 570 passed · `ruff` clean · `mypy` clean (45 files) · boundary OK ·
version 0.2.0. New: `tests/test_work_land.py` (propose_pr branch+push+draft never
merges; held-unit fail-closed; flag ON proposes / OFF read-only; gateway reviewer
threaded, not the mock).
