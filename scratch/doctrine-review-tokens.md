# Adversarial Review — Coordinator Token-Economy Doctrine

**Lens:** Token accounting. **Posture:** refute "saves tokens/context with no downside."
**Verdict (one line):** Net-SAVER for large tasks, net-LOSER for the long tail of small
over-threshold tasks; the doctrine is *true but stated unconditionally when it is conditional*
on task size and remaining session length. The rule-2 trigger is set far too low.

---

## 0. Ground truth from THIS live session (evidence base)

| Sub-session task        | Output tokens spent | Persisted report | Discarded (never hit coordinator) |
|-------------------------|---------------------|------------------|-----------------------------------|
| design/pivot plan       | 91,037              | ~7.0k (27,748 B) | ~84k (92%)                        |
| ticket/backlog filing   | 91,332              | ~2.0k (7,812 B)  | ~89k (97%)                        |
| SLOP doc placement      | 41,409              | ~0.9k (3,710 B)  | ~40k (98%)                        |

The single most important number in this whole review: **~92–98% of each sub-session's spend
was working context (file reads, intermediate reasoning, dead ends) that was DISCARDED at the
pointer boundary and never entered — and never re-billed against — the coordinator.** That
discard ratio is what the doctrine actually monetizes. It is real and it is large.

---

## 1. Explicit net-token model

### 1.1 The two billing mechanics that matter
- **Compounding re-bill (favours delegation):** a token placed in coordinator context is
  re-read as *input* on EVERY subsequent coordinator turn. Inline work permanently inflates
  context by its residue ΔC, taxing all `N_remaining` future turns.
- **Fixed spawn tax (favours inline):** every sub-session re-pays a base it does not share with
  the coordinator — full agent system prompt + tool schemas + injected CLAUDE.md/MEMORY.md
  (this session injects a ~55-line memory index + tool list on *every* sub turn) + the briefing
  it must read + files it RE-reads that the coordinator already held. Call this `Ω`. `Ω` is paid
  once per spawn and, for its input portion, on each of the sub's own turns.

### 1.2 Per-task comparison
Let, for one candidate task:
- `ΔC_inline` = context residue if done inline (working set that STAYS: tool results + output).
- `ΔC_deleg`  = what the coordinator absorbs anyway = briefing `B` written out + pointer `P`
  (+ full report `F` **iff** rule-5 "read when gating" fires).
- `N`         = coordinator turns remaining in the session.
- `r`         = input token price; `f` = cache-discount factor on re-billed input (with prompt
  caching, `f ≈ 0.1`; without, `f = 1`).

**Coordinator compounding cost, inline:**  `ΔC_inline · N · r · f`
**Coordinator compounding cost, delegated:** `(B + P + [F]) · N · r · f`
**Extra system cost of delegating:**         `Ω` (spawn tax; ~pure duplication)

**Delegation net-wins when:**

```
(ΔC_inline − ΔC_deleg) · N · r · f   >   Ω
```

i.e. the compounding context you AVOID must outweigh the fixed spawn tax you ADD.

### 1.3 Break-even threshold (solve for task size)

```
ΔC_inline  >  ΔC_deleg  +  Ω / (N · f)
```

Two regimes fall out immediately:

- **Long session, big task, cache on** (`N≈20`, `f≈0.1`, `Ω≈25k`):
  break-even ≈ `ΔC_deleg + 25k/(20·0.1)` = `ΔC_deleg + 12.5k` tokens of residue.
  The three real tasks (84–89k discarded residue) clear this by ~7×. **Delegate — clear win.**
- **Small over-threshold task** (residue a few k): the `Ω/(N·f)` term (~12.5k) dominates;
  inequality fails. **Inline — delegating INCREASES net system tokens.**

So the doctrine's savings are not a property of the rule — they are a property of *task size
relative to `Ω/(N·f)`*. Rule 2 does not measure that quantity at all.

---

## 2. Strongest refutations of "saves tokens with no downside"

**R1 — The trigger is below break-even, so it mandates net-loss spawns.**
Rule 2 fires on ">1 file OR >150 lines OR *any* code edit OR *any* repo-wide search." A one-line
code edit, or a grep returning five hits, leaves `ΔC_inline` of a few hundred–few thousand
tokens — far under the ~12.5k break-even. For these the spawn tax `Ω` (fresh system prompt +
tool schemas + memory injection + briefing + re-reads) is pure additive waste. The doctrine
*increases* net tokens on the entire long tail of small tasks and calls it savings.

**R2 — Prompt caching guts the headline premise.** "Context is re-billed every turn" is quoted at
full price. With caching it is re-billed at `f≈0.1`. Meanwhile the spawn tax `Ω` lands on a COLD
sub-session cache and is largely paid at full rate. The doctrine implicitly compares a
cache-discounted inline cost against full-rate spawn costs and *still* only wins for big tasks —
strip the discount illusion and the small-task regime looks even worse for delegation.

**R3 — Rule 5's "read the report when gating" voids the pointer economy.** The ≤5-line return
(rule 4) only saves context while the report stays unread. The moment the coordinator must read
`F` to gate a decision (caveat a: gate-critical work is exactly what you cannot trust blind),
`ΔC_deleg` jumps from `~P` to `~P+F`. If `F ≈ ΔC_inline` (a summary-heavy task where the report
IS the work), delegation saved ZERO compounding context and you still paid `Ω`. Pure loss. The
pointer-return is a fiction precisely for the high-stakes tasks the doctrine most wants to gate.
(Note: it survives here because our three reports were 7k/2k/1k vs 84–89k discarded — `F ≪`
working set. That is the *condition* under which rule 4 pays, and it is unstated.)

**R4 — Redistribution, not reduction, when residue is low-entropy.** For a task whose entire
output is retained (e.g. writing a config the coordinator needs verbatim), inline residue and the
delegated report are the same tokens. Delegation just moves them through an extra hop that adds
`Ω`. Net system tokens rise; only the *coordinator's* line-item falls. Optimising the coordinator
sub-metric while raising the system total is the classic redistribution trap.

**R5 — Chain-depth and end-of-session blindness.** Deep A→B→C delegation stacks `Ω` at each level
(system prompt + memory re-injected per hop) and serializes latency with no parallelism payoff.
And `N` shrinks to ~0 near a handoff: with no future turns to amortise against, `Ω/(N·f)→∞` and
delegation is *always* a loss late in a session. Rule 2 is stateless w.r.t. both depth and phase.

**Fair-play concession (keeps the review honest):** for the three real 91k/91k/41k tasks, inline
would have injected ~250k of combined output PLUS their working sets into coordinator context,
re-billed across every remaining turn — a genuine multi-million input-token compounding cost.
Delegation confined it to disposable contexts and returned ~10 lines. That is a large, real net
saving. The claim is not false. It is *unconditional prose over a conditional inequality.*

---

## 3. Concrete narrowing recommendations

**N1 — Replace the rule-2 trigger with an estimated-residue test.** Delegate only when expected
retained residue `ΔC_inline` clears break-even, not on file/line count. Practical proxy:
> Delegate when the task will likely leave **>~10k tokens of context residue** — heuristics:
> **>~400 lines touched, OR >5 files, OR expected output >10k tokens, OR a repo-wide search whose
> raw hit-dump would exceed a screen.** Otherwise inline.
Explicitly **drop "any code edit" and "any repo-wide search" as automatic triggers** — a one-line
edit or a 5-hit grep belongs inline.

**N2 — Add a session-phase gate.** Do not delegate when few coordinator turns remain (near
handoff/end). The compounding term that justifies spawn tax has evaporated. Rule of thumb: if
`N · f · ΔC_inline < Ω`, inline regardless of size.

**N3 — Carve-out for must-read-report (gate-critical) tasks.** If the coordinator will read `F` in
full to gate, delegate ONLY when the sub also discards a working set `≫ F` (i.e. `F ≪ ΔC_inline`,
as in our 7k-report/84k-discard cases). If report ≈ working set, inline — the pointer saves
nothing and you pay `Ω`.

**N4 — Cap chain depth at 1.** Sub-sessions may not spawn sub-sub-sessions; the stacked
system-prompt/memory tax and serialized latency dominate. Fan-out (parallel siblings under the
coordinator) is fine; nesting is not.

**N5 — Price the briefing into the decision (tighten rule 3).** If authoring a briefing complete
enough to prevent re-investigation costs a meaningful fraction of doing the task inline, do it
inline. `B` is written by the coordinator (output) AND read by the sub (input) — it is billed
twice by construction.

**N6 — Right-size with `Ω` in view (tighten rule 7).** Cheap models still pay the full spawn tax
and often have weaker cache behaviour; "cheap model" does not rescue a below-break-even spawn.
Model choice changes work cost, not the spawn/compounding trade that decides delegate-vs-inline.

---

## 4. Bottom line for rollout
Adopt the doctrine, but ship it with the inequality, not the slogan. Keep rules 1, 3, 4, 6, 8 as
written; **rewrite rule 2 (N1) and rule 5's read-back (N3), and add N2/N4** before fleet-wide
rollout. As written it demonstrably wins on the token-volume-dominant big tasks (verified this
session) while quietly taxing every small over-threshold task and every late-session or
must-read-report case. The savings are real; the "no downside" is not.
