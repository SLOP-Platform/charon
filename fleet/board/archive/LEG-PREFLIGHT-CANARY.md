repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/leg-preflight-canary
depends_on:
serial_justified: one canary runner + its task set + test; the probe loop, the leg-pinning, and the rank/gate output are one cohesive primitive.
owns: fleet/benchmark/leg-preflight.sh, fleet/benchmark/preflight-tasks/canary/, fleet/tests/leg-preflight.test.sh, fleet/state/LEG-RANK.tsv
accept: |
  STAGE-1 DUE-DILIGENCE GATE: a FAST (seconds, not minutes) per-(model,leg) canary that proves a leg is
  reachable + actually SERVES a working model (not a stub/degraded/wrong model) + measures performance —
  so we RANK legs and only send the expensive full honest-battery/dogfood (8-min budget) to legs that pass.
  Motivating waste (2026-07-15): minimax-m2.7 burned ~24 min (3×8min rc=124 hangs) on a dead leg with NO
  pre-check; NVIDIA NIM was proven healthy in ~7s by the prototype canary. Reference impl:
  fleet/state/leg-canary-prototype.py (balanced-parens coding task, temp=0, exec-checked 5/5, latency + tok/s).
  DO:
  - fleet/benchmark/preflight-tasks/canary/: a SMALL set (2-3) of short, deterministic, OBJECTIVELY-checkable
    hard-ish tasks (coding one-liner exec-checked + a reasoning exact-answer). Temp=0. Must discriminate a real
    top-tier model from a degraded/quantized/tiny/stub one (include a known-weak control that should score low).
  - fleet/benchmark/leg-preflight.sh <model-or-leg ...> (default: the candidate roster): for each LEG (pin the
    PROVIDER — via a provider-suffixed alias / routing override so we test THAT leg, not cheapest-available;
    document how leg-pinning works against the gateway), run the canary under a SHORT budget (e.g. 60-90s), and
    record per leg: reachable(200+content) · serves-working(canary score) · latency · tokens/sec · error-class.
  - EMIT fleet/state/LEG-RANK.tsv: model, provider/leg, reachable, canary_score, latency_s, tok_s, verdict
    (HEALTHY | DEGRADED-serves-wrong | SLOW | UNREACHABLE), date. A leg that is UNREACHABLE/DEGRADED is proposed
    for park (feeds auto-park-scan / PARKED-MODELS.tsv); a HEALTHY+fast leg is eligible for the full test.
  - GATE hook: the honest-battery sweep / dogfood-eval consults LEG-RANK and SKIPS a model whose every leg is
    non-HEALTHY (the pre-flight availability gate we lack today — [charon-north-star-engine-mechanism]); this is
    the cheap front half of the S8 >=1-viable invariant (full hold/re-probe lifecycle stays in GRACEFUL-DEGRADE).
  - NEVER trust the model's word — the canary VERDICT is the exec/exact-match check, not the model's output prose.
    Non-Anthropic only (sg-never-anthropic).
  REVIEW ADD-ONS (MODEL-TESTING-ADVERSARIAL-REVIEW.md): F6 — the ranking harnesses call BASE pool ids that route
  cheapest-available, so per-provider rank is IMPOSSIBLE today (dogfood-eval.sh:328 admits it). Make leg-pinning
  END-TO-END: leg-preflight AND the dogfood/sweep path must accept a LEG-SUFFIXED / provider-pinned id (like the
  prototype's nvidia/… and the existing -ds/-cb/-together aliases) and either disable the gateway's internal
  cross-provider failover for a ranking run OR correlate the gateway request-log by request-id to recover which leg
  served — so a rank is per (model,LEG), not an average over whatever served. F14 — run the canary's exec-check of
  MODEL-EMITTED code in a SUBPROCESS with a resource/ulimit/seccomp boundary (the prototype's bare exec() is a
  supply-chain hole once productionized).
  FAIL-ON-REVERT (fleet/tests/leg-preflight.test.sh, hermetic — stub the gateway): a stubbed HEALTHY leg (fast,
  correct canary) ranks HEALTHY + is eligible; a stubbed leg that returns wrong/empty content ranks DEGRADED +
  is gated OUT; a stubbed unreachable/timeout leg ranks UNREACHABLE + proposed-park; the sweep-gate hook skips a
  model whose only leg is UNREACHABLE. Revert the gate -> the dead-leg model is sent to the full test -> test fails.
