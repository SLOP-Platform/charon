# Task: evaluate a design tradeoff

Two approaches for caching model responses in the gateway are proposed:

**Approach A — in-process LRU cache, 60s TTL, 1024 entries.**
- Pros: zero network latency, simple eviction, no external dependency.
- Cons: per-process state means the cache is cold for every new worker
  and cannot be shared across multiple gateway replicas; eviction
  policy is approximate (LRU ignores access frequency).

**Approach B — external Redis cache, 5-minute TTL, key = hash of the
  request payload.**
- Pros: shared across all gateway replicas, persistent across worker
  restarts, exact-match keys (no false-positive stale reads).
- Cons: ~1ms network latency per cache lookup, requires a Redis
  dependency + ops burden, must handle Redis outages.

You are writing the design tradeoff section of an ADR (Architecture
Decision Record). Write a 3–6 sentence analysis to `answer.txt` that:

1. Identifies which approach is better for a HIGH-THROUGHPUT, MULTI-
   REPLICA production gateway (most-cached items are short prompts
   that fit in a single response, hit rate ~70%).
2. Names ONE specific failure mode each approach has in that scenario.
3. Recommends a concrete mitigation for the chosen approach's failure
   mode.

The grader checks the answer covers the three required points above
(keyword + structural checks; the prose itself is not graded). Format
your answer as plain text, with the three points clearly separated
(e.g. numbered list, blank lines, or clear sentences).
