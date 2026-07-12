# PROPOSAL — Session process-discipline guardrails (two-tier, harness-agnostic)

**Status:** DTC-REVIEWED → **REVISED & APPROVED 2026-07-11** (5-decision walkthrough) · **Author:** manager session (kit-fisto successor)

## DTC OUTCOME — revised design (this supersedes §5–§7 below)
The 4-lens DTC (`state/reviews/DTC-guardrails-*.md`) REJECTED the git-hook-first sequencing. Approved revision:
- **D1 ✅ CI required check = the real enforcement** (`charon.cli gate`, repo-bound, un-bypassable, CG-reaching, re-runs verification → kills false-green). Promoted to FIRST.
- **D2 ✅ DROP the git pre-push hook entirely** (would brick every push via `project-audit.sh` exit-2; zero CG reach; `/home/stack` product-leak). Recover the local-nudge as advisory text in the rules.
- **D3 ✅ Gate in `land-push.sh`** (rig-side → has board/reviews inputs, no leak; already sits on the CG-landing push). My §7 "refine to git hook" was WRONG; land-push was right.
- **D4 ✅ Fold the 4 disciplines into `MANAGER-OPERATING-RULES.md`** (one SSOT; JOIN-PROMPT + CG AGENTS.md reference it, don't duplicate).
- **D5 ✅ DEFER gateway injection** (§5 step-3) — high blast radius; wake-trigger `cg-drift.sh` (≥2 CG discipline failures / 30d) fires loudly when warranted. Parked ticket `GATEWAY-CONTRACT-INJECT`.

Sections §5–§9 below are the pre-DTC proposal, retained for the record. **Build order now: D1 → D3 → D4; D2 dropped; D5 parked behind the trigger.**

## 1. Problem
Manager/droid sessions keep repeating four **process-discipline** mistakes (all hit this session):
- **(a)** building/authoring work without first scanning existing tickets/branches/commits → repeat-work / collisions.
- **(b)** merging key / "money-path" work without an adversarial review.
- **(c)** verification mistakes — misreading a piped exit code (`| tail; echo $?`), trusting "green" without proof.
- **(d)** trusting docs/docstrings over reading real code.

We build via **two harnesses**: Claude Code (manager + `claude -p` droids) and **opencode/"CG"** (an OpenAI-compatible gateway; a different harness). **Claude Code hooks + permissions bind only Claude sessions — they do not reach CG.** That CG gap is the central hard constraint.

## 2. Decision drivers
- Operator lens: **simple, elegant, low-overhead, cheap, anti-sprawl** — reject anything that merely duplicates native hooks or the fleet rig.
- **Blast radius** is a first-class ranking axis: prefer the lever whose worst-case failure is smallest and most reversible.
- Must **reach CG**, not just Claude.

## 3. Rejected alternatives (adopt nothing wholesale)
Five options evaluated (`fleet/state/reviews/GUARDRAIL-EVAL-*.md`):
| Option | Verdict | Reason |
|--------|---------|--------|
| Qodo | REJECT | Post-hoc PR-review SaaS; wrong layer; credits + code egress; no CG reach |
| ghost-in-the-loop | REJECT | Browser chat-autopilot; *reduces* oversight; DOM-bound; AGPL |
| awman | REJECT whole | Heavyweight Rust/Docker orchestrator — a peer to our rig; anti-sprawl-hostile |
| addyosmani/agent-skills | BORROW | On-target (MIT, 77k★) but uses hooks (doesn't beat them); no CG runtime reach |
| Third-party "LLM guardrail" fwks (Guardrails-ai/NeMo) | REJECT | Content/schema validators — wrong shape |

**Nuggets kept:** machine-gradable JSON verdict shape (Qodo); `[[HALT]]/[[NEEDS-REVIEW]]` structured token (ghost); prompt-preamble guidance injector for CG (awman); `doubt-driven-development` + `code-review` skills and the "Rationalizations" anti-excuse table (agent-skills); PR-Agent as an *optional* free reviewer engine behind our own gate.

## 4. The architecture — two tiers, one shared contract text
The four disciplines split by **where the mistake becomes observable**:
- **(a-partial) + (b)** end in a git/CI **artifact** → a chokepoint every actor (Claude, CG, human) must pass → **HARD-enforceable, harness-agnostically.**
- **(c), (d), early-(a)** live in model reasoning + the agent's local shell → **no chokepoint** → only **steerable** by prompt-content and **caught later** by an independent re-check.

Therefore:
- **Tier-1 (advisory, shape behavior):** ONE discipline-contract text, delivered by TWO pipes so it reaches both harnesses — Claude via the existing SessionStart hook; CG via gateway prompt-injection.
- **Tier-2 (hard gate, catch what advice missed):** enforcement at the git/CI artifact chokepoint — binds the **repo, not the session**, so it fires for CG identically to Claude/human.

## 5. Sequenced rollout (blast-radius ordered — cheap/contained first, money-path last)
| Step | Layer | Reaches CG | Blast radius | Reuses |
|------|-------|-----------|--------------|--------|
| **1** | committed `.githooks/pre-push` (`git config core.hooksPath .githooks`): refuse a push whose branch lacks a prior-work scan pass **(a)** or whose money-path diff lacks a review trailer **(b)** | ✅ harness-agnostic | 🟢 tiny — fails one push on one box; `--no-verify` escape; one-line delete | `project-audit.sh` (exit 2 = collision) |
| **2** | CI required checks: no-collision **(a)**, required adversarial-review status on protected paths **(b)**, and **CI re-runs the claimed verification (c)** — the only place a false "green" is truly defeated | ✅ un-skippable | 🟡 blocks merges, never traffic | project-audit + gate |
| **3** | Gateway contract injection (~5 lines at `forwarder.py:113-123`, the only behavioral CG lever) for **(c)/(d)** | ✅ behavioral | 🔴 maximal — 100% of money path → flag-guarded, **fail-open**, **byte-identical-off**, cloned from the `forwarder.py:121` guard; shipped LAST | contract text |

**How the CG gap closes:** same contract text via two pipes (SessionStart hook for Claude, gateway injection for CG) for the *behavioral* half; repo-bound git/CI gates for the *enforceable* half. Native hooks handle only the Claude behavioral half.

## 6. First step (the only thing built now)
A committed **`.githooks/pre-push`** that hard-gates (a)+(b) by shelling out to `project-audit.sh` + a `Reviewed-by:`/`Review:` trailer check on money-path diffs. Chosen first because it is **harness-agnostic (reaches CG), lowest-blast, near-zero cost, fully reversible**, and needs no shared-runner coordination. CI is the correct *second* step; the gateway lever is deliberately *last*.

## 7. Refinement of the prior decision (explicit, not silent)
The review-gate was approved as a **hard-block in `land-push.sh`**. `land-push.sh` is **Claude-only** (it's the manager's push lever, gated by the permissions deny-list). Moving the same enforcement into the **git `pre-push` hook** makes it harness-agnostic (reaches CG), lowers blast radius, and mechanizes the audit-gate + review-gate in one ~30-line hook. `land-push.sh` remains as the manager's autonomous-push convenience; the *gate* moves to the hook. Trigger unchanged: `work_class: money-path` ∧ `difficulty ≥ 4`; reviewer ≠ builder; `--no-verify`/CI-override as the logged escape.

## 8. Companion (already approved)
**Backfill review-debt audit** (a *mode* of the review tooling): scan already-merged tickets meeting the review-required criterion with **no** review record → emit a **ranked review-debt list** (operator chooses what to retro-review; not auto-launch).

## 9. Open risks for the DTC to probe
- Does CG/opencode actually **push via git** in a path the hook intercepts, or does a human/land-push do the final push? (If CG never pushes, the hook's CG reach is theoretical.)
- `core.hooksPath` is **repo/user-global** — does setting it clobber or bypass any existing hooks? Reversibility of activation.
- `--no-verify` makes step 1 bypassable → does it become theater without step 2 (CI)? Is shipping step 1 alone worthwhile?
- Review-trailer convention: who writes it, how is "reviewer ≠ builder" actually verified by a hook that only sees a diff?
- Gateway injection data-egress: contract text ships to third-party providers every call — keep generic, no repo internals (`[public-repo-no-personal-info]`).
- Sprawl check: git-hook + CI + gateway + skill/MCP — is this *more* moving parts than the problem warrants? Could a subset deliver 90%?
