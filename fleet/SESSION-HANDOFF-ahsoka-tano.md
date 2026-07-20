# Charon — Session Handoff — ahsoka-tano

**Session:** ahsoka-tano
**Date:** 2026-07-19

## Bootstrap (copy-paste into next session)
```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-ahsoka-tano.md — start with the DIRECTION and the "do first" security fix.
```

## DIRECTION (lead here — do not lose this; anchored so it can't drift)
**Charon = an outcome-graded gateway.** Adopt the commodity substrate, build only the ~30% novel slice.
- Canonical: **ADR-0017** (`docs/adr/0017-outcome-graded-gateway.md` on product master) + its amendment.
- Doctrine (fires every session): `adopt-substrate-build-only-novel-slice` — SSOT Charon PR #138, SLOP CLAUDE.md PR #9.
- Memory: `charon-strategy-outcome-graded-gateway`. Full reasoning: `/home/stack/worktree-salvage-20260719/` (8 SURVEY/REVIEW/EVAL + DECISION-RECORD).
- **MVP = wire the fleet's existing outcome-graded brain into the gateway request router** — needs a prerequisite (product has no outcome store) + a cold-start seed. Two tickets: `PRODUCT-GRADES-STORE` then `WIRE-BRAIN-INTO-GATEWAY`.
- LiteLLM substrate: PROVEN by spike (ADOPT-SUBSTRATE-01). Gitea Actions CI: PROVEN by spike (cutover viable).

## VERIFIED STATE (queried, not asserted — 2026-07-19)
- product `origin/master` = **eeb93b9** · rig `origin/master` = **6d475a5** (fetched). Sync local before trusting; `validate_board.sh`/land-push board gate are only accurate in the LIVE tree, NOT a worktree (false-REDs — point land-push `$REPO` at the live tree).
- Open **product** PRs: #172 #169 #164 #161 #135 #86 (pre-existing, not this session's — mostly stale/hand-rolled-rig class).
- Open **rig** PRs: #119 #116 #114 #105 #97 #96 #95 #93 #47 (older stranded rig work; hand-rolled-gate class → park under retire-the-rig, don't rebuild).
- Rig tree clean apart from the 2 new board tickets (committed by this handoff) + untracked `.ksf/`.

## DO FIRST next session — the security fix (deferred, ticketed)
**`fleet/board/FIX-PROVIDER-KEY-EXFIL.md`** — CONFIRMED provider-API-key exfiltration, 3 bypasses across 2 fix rounds. Pre-existing; exposure narrow (token-gated, lan_open_ui abandoned) but REAL. Partial fix preserved on branch **fix/provider-key-exfil @ d83ce9a** (closes the no-key path; the fresh-key escape hatch STILL leaks). Root cause = the shared `key_env` env-var-NAME indirection. **Prefer the elegant redesign** (per-provider secret keyed by provider id, removing the indirection) over patching — see the ticket `blast_radius_note`. Adversarial re-review mandatory (keys/money path, 3/3 rounds found a bypass). Do this BEFORE adding new providers.

## Landed this session (verified merged)
Rig: #138 (adopt-substrate doctrine), #139 (handoff generate-state). Product: #176 (gate-runner fail-closed), #177 (ADR-0017), #178 (ADR hygiene + 0011 renumber), #180 (ADR amendment). Earlier rig safety wave (#121 first-ever rig CI, #123 reaper, #124 land-push CI, #125 dogfood guards, #126 droid-reap, #127–#130) all merged.

## Parked / abandoned (with reasoning — closed ≠ abandoned)
- 5 rig prevention-tool PRs (#131/#133/#135/#136/#137) **parked** under retire-the-rig. #135 held a real fail-open safety fix → carry its intent into Semgrep.
- **CG-LAN-OPEN-UI abandoned** (`fleet/board/CG-LAN-OPEN-UI.md` marked): introduced a key-exfil hole; superseded by the existing `/charon/login` session-cookie flow (already a simple browser auth layer — use it; tinyauth/Traefik only if you want fancier later).
- C1-10P dropped from the runner pool (too slow).

## Next-session items
- `/home/stack/worktree-salvage-20260719/NEXT-SESSION-ITEMS.md` — **operator wants Alibaba Cloud (Qwen/DashScope, OpenAI-compatible) added to CG** via the `charon` CLI. AFTER the key-exfil fix (it changes key validation/send).
- Gitea Actions **cutover** (spike PASSED): make it CI authority, optionally mirror marketplace actions. Runner durable on BB-8.
- Gateway MVP: `PRODUCT-GRADES-STORE` → `WIRE-BRAIN-INTO-GATEWAY` (ledger name `outcomes.py`, provider seam `routing_policy/` — operator-confirmed).

## Infra state (NEW — carry it)
Memory `charon-host-inventory`. **Gitea LIVE** on c1-10p:3000 (`stack/charon` migrated; admin `stack`; API token on c1-10p `~/gitea-token`, lacks read:user). **Public mirror** on c1-10p (anon cron, token-free). **act_runner durable** on BB-8 (systemd, label `charon-ci`). GitHub Actions had a partial OUTAGE; product `CI_RUNNER` **UNSET → GitHub-hosted fallback** (re-set to `["self-hosted","charon-ci"]` once the pool is finished; **charon-ci relabel of 4-LOM's 3 runners + BB-8 registration STILL PENDING** on the outage). Hosts: 4-LOM fast (10.0.1.60, 3 runners + gateway), BB-8 mid (10.0.1.61), Wyse 5070s weak (c1-10p .52, Rocinante .51, 0-0-0 .50 = PrismLinux/Arch, LO-LA59). Merge queue blocked (free plan). Auto-delete-head ON both repos.

## OPERATOR-PENDING (exact commands)
- Rotate the Gitea token (pasted in chat): Gitea → Settings → Applications; regenerate WITH `read:user`.
- Finish runner pool when GitHub Actions recovers: next session re-runs the `charon-ci` relabel + registers BB-8's runners; you decide when to re-set `CI_RUNNER`.

## Gotchas
`git merge/rebase/reset/merge-base` DENIED to manager; push only via land.sh/land-push.sh. Tool output lies both directions — verify with `gh pr view --json state` + present-on-master. One agent per worktree. `.output` mtime is NOT agent liveness. Handoffs auto-generate a verifiable state block (#139) — regenerate via handoff.sh rather than hand-writing.
