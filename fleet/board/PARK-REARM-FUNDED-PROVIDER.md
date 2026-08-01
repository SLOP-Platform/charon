repo: charon
tier: strong
priority: 0
difficulty: 3
work_class: money-path
branch: fix/park-rearm-funded-provider
depends_on: SW-IDENTITY-FOLD
real-dep: SW-IDENTITY-FOLD shares src/charon/proxy.py and is now PUSHED awaiting merge — sequence after it lands, not a build prereq
owns: src/charon/proxy.py, tests/test_park_rearm.py
serial_justified: |
  One classification rule and one re-arm path, both on the same exhaustion decision. Splitting
  ships either a classifier with nothing to re-admit, or a re-arm for a state nothing sets.
source: |
  Measured 2026-08-01. Operator: "openrouter still has $2.78 of balance" while the gateway
  reports it parked/drained/cooled.
note: |
  ## THE DEFECT — ONE MODEL'S CAP PARKS AN ENTIRE FUNDED PROVIDER, WITH NO WAY BACK
  Measured on the live 4-LOM gateway:
  - `src/charon/proxy.py:41` — `_EXHAUSTION_STATUSES = {429, 402, 503}`.
  - The `gpt-5.4-mini` leg returned **402 "Insufficient USD balance. Available 0.050538 USD,
    required 0.153460 USD"** — a PER-KEY/PER-MODEL cap.
  - 402 -> exhausted -> drain-then-park parked **the whole `openrouter` provider**.
  - The provider still holds **$2.78** and is still serving traffic: probes for `glm-5.2`,
    `deepseek-v4-flash`, `minimax-m3-free`, `kimi-k2.6` all returned 200 via its upstreams
    (Decart, StreamLake, Novita, Baidu) WHILE it was reported parked.
  - Droid launch banners now read: `2 provider(s) parked/drained/cooled (huggingface, openrouter)`.
  - `/data/balance_park.json` lists ONLY `huggingface`, so openrouter is on a RUNTIME cooldown —
    invisible on disk and not clearable by editing state.
  - **`/data/balance.json` DOES NOT EXIST**, so nothing can re-arm on observed balance.

  ## WHY IT MATTERS (money-path)
  A funded provider is being treated as drained. Consequences: the pool is thinner than it is,
  routing may deprioritise or skip a leg that works, and the operator's balance goes unused. It
  also makes every "POOL TOO THIN / ALL-EXHAUSTED" signal untrustworthy — we cannot tell a real
  exhaustion from a mis-parked provider.

  ## THE TWO BUGS — FIX BOTH
  1. **BLAST RADIUS IS WRONG.** A 402 on ONE model/key must not park the PROVIDER. Park the
     narrowest thing the evidence supports: that leg/model. Provider-level park requires
     provider-level evidence (e.g. an account-balance signal), not a single leg's cap.
  2. **NO RE-ARM.** A parked provider that starts answering again must be re-admitted. The
     funding-class re-arm table exists (`balance.py` park/unpark, per the drain-then-park work)
     but did not fire here — determine whether it is unwired, or wired but starved of the balance
     data it needs. **Do not build a second re-arm** — find why the existing one is silent.
     Reuse-check `src/charon/balance.py` and `degrade_alert.py` FIRST.

  ## ALSO ANSWER (do not skip — it may be the real root)
  Is the missing `/data/balance.json` the cause? `R46 balance-wire` is marked Done and
  `_build_balance_tracker` is said to construct from gateway config. If the tracker has no
  persisted balance, is every provider effectively unknown-balance, and does that make park
  decisions unrecoverable by construction? Answer with evidence.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, offline, stubbed upstream — no live gateway:
    a. **Reproduce**: a 402 on ONE leg does NOT park sibling legs of the same provider.
       Revert the narrowing -> RED. This is the live defect.
    b. a parked leg that answers 200 again is RE-ADMITTED within a bounded window.
       Revert the re-arm -> RED.
    c. a genuine provider-wide exhaustion (account balance zero / all legs 402) DOES still park
       the provider — ANTI-OVER-BLOCK. Without this the ticket removes a real protection.
    d. 403 key-limit is classified distinctly from 402 balance-exhausted, and neither is silently
       folded into the other. Both must be visible in the exhaustion ledger with the right label.
  Then dogfood against the live gateway: show openrouter re-admitted and serving, with its
  reported state matching reality.

  ## ADVERSARIAL REVIEW REQUIRED (money-path)
  This changes when the gateway stops using a paid provider. Reviewer != builder. The reviewer
  must confirm the narrowing cannot let a genuinely drained provider keep taking traffic and
  burning failover slots.

D&S — Deps & Sequence:
  - Independent of FORWARDER-COST-ORDER-FALLBACK (that one fixes ORDER; this one fixes
    EXCLUSION). Both touch routing but different decisions — check for an owns collision on
    forwarder.py before starting and sequence if needed.
