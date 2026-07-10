# Coordinator token-economy doctrine — empirical measurement

**Claim under test:** delegating substantive work to sub-sessions that write-to-file and
return ≤5-line pointers (keeping the coordinator lean) SAVES tokens/context without slowing
things down.

**Verdict (one line):** HOLDS strongly for COORDINATOR-CONTEXT tokens on large,
many-turns-remaining work; is a WASH-to-LOSS on TOTAL system tokens and on wall-clock for
small or end-of-session tasks. Delegation is a re-billing-avoidance trick, not a work-cheapening one.

Confidence: DIRECTIONAL, small-N (1 natural experiment with 3 delegations + 1 controlled A/B).
The mechanism (per-turn context re-billing) is certain; the multipliers (remaining-turns R,
sub-agent fixed overhead) are estimated and labeled.

---

## The mechanism (why this is even a question)

In an agent loop, every assistant message and every tool-result is appended to the transcript
and **re-sent as INPUT tokens on every subsequent LLM call in that session**. So an artifact of
size S tokens placed in the coordinator's context is not paid once — it is paid ~S on each of the
remaining coordinator turns. A **sub-agent's context, by contrast, lives only inside its own
bounded loop and is DISCARDED when it returns** — only its ≤5-line pointer survives into the
coordinator. That asymmetry is the entire savings.

---

## (1) Natural experiment — this live session (real token counts)

Three substantive tasks were delegated. Measured sub-session OUTPUT tokens:

| task | sub-session output tokens |
|------|--------------------------:|
| A    | 91,037 |
| B    | 91,332 |
| C    | 41,409 |
| **sum** | **223,778** |

**Counterfactual: same 3 tasks done INLINE in the coordinator.**

(a) Context that would be added to the coordinator transcript.
Doing the work inline appends the assistant's generated tokens (reasoning + tool calls + any
file-write payloads) to the coordinator's own transcript. Output tokens are a **conservative
LOWER bound** for that growth (inline would ALSO append every file/tool-result the sub-agents
read as input — not counted here). So inline context growth ≥ **223,778 tokens**.

Delegated reality: the coordinator paid only brief-authoring (~150–400 tok each) + the returned
pointers (≤5 lines ≈ 60–100 tok each). Call it ~500 tok/task round-trip × 3 ≈ **~1,500 tokens**.

Immediate coordinator-context delta at the moment all 3 finish:
**≈ 223,778 − 1,500 ≈ 222,000 tokens leaner (lower bound).**

(b) Remaining coordinator turns R after the delegations.
Unknown; a manager session keeps gating/merging/dialoguing afterward. I present a range rather
than invent a number: R ∈ {3, 10, 15}.

(c) Compounded coordinator-context input cost (the delta re-billed each remaining turn):

| R (remaining turns) | inline extra input re-billed (222k × R) | delegated (1.5k × R) | coordinator-tokens saved |
|--------------------:|----------------------------------------:|---------------------:|-------------------------:|
| 3  | ~666,000  | ~4,500  | ~662,000 |
| 10 | ~2,220,000 | ~15,000 | ~2,205,000 |
| 15 | ~3,330,000 | ~22,500 | ~3,308,000 |

Even at a stingy R=3, keeping those 3 tasks out of the coordinator saves on the order of
**0.66M re-billed input tokens**; at R=10, **~2.2M**. This is the compounding: savings scale with
(artifact size) × (turns remaining).

**Assumptions/caveats:** output tokens used as a proxy for inline context growth (lower bound —
real figure higher). R is genuinely unknown; table shows sensitivity, not a point claim. Assumes
no prompt-cache; caching would blunt but not erase the re-billing (cache is per-session/TTL-bound
and still charges cache-read on the growing prefix).

---

## (2) Controlled mini A/B — real, measured

Task (bounded, representative): "summarize the structure of
`/home/stack/charon-private/fleet/reds.tsv` and list its columns." File = 7,953 bytes / 25 lines
≈ **~2,000 tokens**. Same task done both ways in THIS session:

| metric | (A) INLINE (I read it myself) | (B) DELEGATED (Explore sub-agent → pointer) |
|--------|------------------------------:|--------------------------------------------:|
| coordinator-context added | ~2,000 tok (full file in my transcript) | ~170 tok (brief ~90 + 3-line summary ~80) |
| wall-clock | ~2 s (one Read round-trip) | **24.3 s** (measured: spawn+read+return) |
| total system tokens | ~2,000 (file) + tiny | ~2,000 (sub-agent re-reads file) + Explore system-prompt overhead (~few k) + brief/pointer → **MORE than inline** |

Both arms produced the identical correct answer (columns: id, opened, severity, area,
description, check_cmd, status, closed_by; 17 data rows; append-only "reds" defect registry).

**What the A/B proves:**
- Coordinator-context: delegation cut 2,000 → 170 (~1,830 tok saved) — real.
- Total tokens: delegation cost MORE (sub-agent re-read the file AND carries a large fixed
  system-prompt; the coordinator's brief/pointer is pure addition).
- Wall-clock: delegation was **~12× SLOWER** (24.3 s vs ~2 s) run serially/foreground.
- **This task is a leaf** (no coordinator turns remain after it), so R≈0 → the 1,830-token
  context saving buys nothing here. Textbook illustration that delegation only pays when R is large.

---

## Coordinator-context vs TOTAL tokens — the honest split

- **Coordinator-context tokens (re-billed per turn):** delegation wins whenever the inline
  artifact S > the pointer P (≈100 tok) — i.e. almost always. Magnitude of the win = (S−P) × R.
- **TOTAL system tokens (sum over all agents):** delegation does NOT make the work cheaper — the
  223k output tokens are spent in sub-agents either way, PLUS each sub-agent's fixed system-prompt
  overhead PLUS the coordinator's brief. On TINY tasks / few remaining turns, delegation's total
  is **higher** (see A/B). It only becomes a total-token win when inline re-billing (S × R) would
  exceed the sub-agent's one-time fixed overhead — i.e. big artifact AND long remaining session,
  because the sub-agent's own internal re-billing is bounded by its short loop, not the parent's.

---

## Empirical break-even (when delegation costs MORE than it saves)

Delegation saves TOTAL tokens when inline re-billing beats delegated fixed overhead:
  (S − P) × R  >  O_sys + B
with measured/estimated constants P≈100, brief B≈200, sub-agent fixed system-prompt O_sys≈3,000:

  **S_breakeven ≈ (O_sys + B)/R + P**

| remaining turns R | break-even artifact size S |
|------------------:|---------------------------:|
| 1  | **~3,300 tok** (only delegate big things if the session is nearly over) |
| 5  | **~740 tok** |
| 10 | **~420 tok** |

Below these sizes, inline is cheaper on total tokens (spawn + re-read + sub-agent system prompt >
what you'd re-bill inline). For COORDINATOR-CONTEXT alone the break-even is far lower (~P ≈ 100
tok) but the saving is only worth the ~20 s latency when S × R is material.

Rule of thumb: **delegate when the task will leave >~1k tokens of artifact AND several coordinator
turns remain; do it inline when it's a sub-~500-token lookup or the session is about to end** —
UNLESS you background the delegation (see below), which removes the latency objection.

---

## The "without slowing things down" clause

FALSE for serial/foreground delegation of a small task: measured 24.3 s vs ~2 s (12×). It becomes
TRUE only when the delegation runs in the BACKGROUND concurrently with other coordinator work — the
sub-agent's wall-clock is then hidden behind work the coordinator does anyway. (The harness itself
flags this: background-by-default unless it's a genuine sub-minute lookup.) So the doctrine's
"no slowdown" claim is conditional on concurrency, not free.

---

## Bottom line

- Coordinator-context savings: **real and large**, compounding as (artifact size) × (remaining
  turns). Natural experiment: ~222k tokens kept out of the coordinator, worth ~0.66M–2.2M re-billed
  input tokens over a plausible R=3–10.
- Total-token savings: **only above the break-even** (~0.4k–3.3k artifact tokens depending on R);
  below it, delegation is a net LOSS.
- Speed: neutral-to-worse unless delegations run in the background.
- Confidence: mechanism certain; magnitudes directional (N=1 session + N=1 A/B). Numbers are
  lower-bounds/estimates as labeled, not fabricated precision.
