# charon-fleet — THE canonical way to build Charon (robot mode)

**Read this before launching any build work. Do NOT revert to bare `claude --bg` with
per-ticket commands** — that caused every WAVE-1 problem (collisions, main-checkout
contamination, the #7 wrong-base merge, the editable-install hijack). This rig is the
fix: one identical command per tab, droids self-claim from a board, each in its own
worktree, propose-default (PR; the operator merges).

This is the operator's **build-rig** for Charon — it lives here in `charon-private/`,
NOT inside the Charon repo (the DTC said the fleet is not a Charon *product* feature;
it IS the right tool to *build* Charon). It is a trimmed adaptation of the audited
mediastack harness (`/home/stack/code/droid-harness/`), with two deliberate changes:
**propose-default landing** (PR, never auto-merge-to-main) and **ephemeral-per-ticket**
(each session does ONE ticket then exits; the launcher relaunches — no warden/reaper/
context-drift).

## Launch a droid (THE one command per tab)
Open a terminal tab and run exactly one of these (tier = which model pool it drains):
```
bash /home/stack/charon-private/fleet/fleet-droid.sh opus
bash /home/stack/charon-private/fleet/fleet-droid.sh sonnet
bash /home/stack/charon-private/fleet/fleet-droid.sh haiku
```
Run as many tabs as you want (e.g. 2 opus + 1 sonnet). Each tab loops: claim a
tier-eligible ticket → run ONE visible `claude` session that makes a worktree, does the
work, opens a DRAFT PR (base master), marks it submitted → claim the next → stop when its
tier is drained. A freed Opus droid will drop down to drain Sonnet/Haiku tickets.

## You are the MANAGER (this is the overseeing session)
```
bash /home/stack/charon-private/fleet/status.sh    # FULL dashboard: live droids + board + PRs + CI
bash /home/stack/charon-private/fleet/board.sh     # quick: just ticket states
gh pr checks <n> --repo SLOP-Platform/charon       # CI gate for a specific PR
# after you review + merge a PR on GitHub, unblock its dependents:
bash /home/stack/charon-private/fleet/done.sh N1
```
`status.sh` is the team_status.sh equivalent — but it reports GROUND TRUTH (live `ps`
processes + git + PR/CI state), not mediastack's heartbeat/token proxies (Charon-Fleet
has no heartbeat/warden, so a droid is "working" iff its tab process is alive + holds a
claim).
Merge order is enforced by `depends_on` (e.g. T7 stays `blocked` until you `done.sh N1`).

## The board
`board/<id>.md` = `tier` + `branch` + `depends_on` + `owns` + a `prompt:` pointer (to
`charon-private/prompts/<id>.md`). To add work: drop a new `board/<id>.md` + its prompt.
Tickets in one wave own **disjoint files**; cross-wave file collisions are sequenced via
`depends_on`. Current board: N1, N2, T8 (ready) · T7 (after N1) · N4 (after N2).

## State (auto-managed)
`state/claims/<id>` held · `state/submitted/<id>` PR open · `state/done/<id>` merged.
`state/lock` is the flock that makes claims atomic. To reset a stuck ticket:
`release.sh <id>`. To wipe all state and restart: `rm -rf state/`.

## Rules baked into every droid (JOIN-PROMPT.md)
own only your ticket's files · worktree off master, never the main checkout · keep the
gate green (`pytest`/`ruff`/`mypy`/`check_boundary`/`check_version`) · stdlib-only core ·
no `pip install -e` · no secrets in the repo · **draft PR base master, never merge**.

## Why not Charon itself?
Charon can't self-orchestrate yet — `run_parallel`/decompose/land/the worker-spawn are
exactly the unbuilt work (ADR-0007/0008). This rig builds that. Once `charon land` + the
engine ship, the build can migrate onto Charon and dogfood itself. Until then: this rig.
