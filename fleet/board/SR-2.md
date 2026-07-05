tier: strong
branch: feat/sr-2-serve-downgrade-stream-cache
depends_on: SR-1
real-dep: SR-1 build — SR-2 reworks the SAME classify()/failover-loop decision SR-1 corrects; the
  namespaced-echo fix must land FIRST so SR-2 only has GENUINE downgrades left to serve. True
  build/correctness prereq, not merge-order. Owns are disjoint (SR-1 proxy.py + test vs SR-2
  proxy_server.py) — the dep is JUSTIFIED, not assumed.
owns: src/charon/proxy_server.py
prompt: /home/stack/charon-private/prompts/sr-2.md
scope: W2. Serve genuine downgrades with the X-Charon-Downgrade header instead of discard-and-rebill;
  bundle the streaming-200 cache fix (same file). Single owner of proxy_server.py in W2. Also writes a
  docs/REVIEW-LOG.md entry for the 2026-07-03 silent-downgrade double-bill incident + registers the
  matching no-double-bill row in docs/DECISIONS.md (append-only shared registers — doc deliverables,
  NOT added to owns).
