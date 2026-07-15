repo: charon
tier: strong
difficulty: 3
work_class: routing
branch: feat/ft-quota-engine
depends_on:
serial_justified: one cohesive module (quota.py) + its test; windows and persistence are the same data structure and must land together.
owns: src/charon/quota.py, tests/test_quota.py
accept: |
  Make the (currently inert) QuotaTracker a COMPLETE free-tier enforcement engine so the wiring
  ticket (FT-WIRE) can trust its verdicts across restarts and real reset cadences. quota.py today
  only does rolling RPM/TPM (60s) + RPD/TPD (86400s) sliding windows, in-memory, no persistence.
  DO (src/charon/quota.py, keep the should_skip/record/get_wait_time API stable):
  - WINDOWS: add WEEKLY and MONTHLY windows (nanogpt weekly input-token cap; mistral ~1B tokens/month)
    alongside the existing rolling ones. Add per-limit `reset` semantics: "rolling" (today's behavior)
    vs "calendar" (resets at a fixed anchor — UTC midnight daily / Monday weekly / 1st monthly). A limit
    declares its kind; should_skip evicts/compares against the correct boundary. Default stays rolling
    (back-compat: an existing {"rpm":500} config behaves exactly as today).
  - PERSISTENCE: usage counters MUST survive a gateway restart or the daily/weekly/monthly counts are
    wrong (a restart currently zeroes them). Persist usage to <state_dir>/quota_usage.json using the
    EXACT atomic-write discipline in balance.py (unique tmp = pid+tid+uuid, os.replace, _save_lock,
    best-effort swallow — the b8e62d0 concurrency-BLOCKER fix; reuse it, do NOT hand-roll). Load on
    construct, save on record(); a corrupt/missing file degrades to empty (fail-open on load only).
  - Keep it stdlib-only and OFF any async loop (quota is called synchronously from the router).
  FAIL-ON-REVERT (tests/test_quota.py, extend): (a) a MONTHLY tpm-style cap blocks the (N+1)th token
  over a month boundary and a calendar reset clears it — assert against an injected clock; (b) record N
  requests, construct a NEW QuotaTracker pointed at the same state file, assert the count PERSISTED
  (revert persistence → the new instance sees 0 → test fails); (c) a rolling window still behaves
  exactly as before (no regression). Reuse the injected-clock pattern already in test_quota.py.
