repo: charon
tier: frontier
priority: 0
difficulty: 4
work_class: fix
branch: fix/money-security-lane
depends_on:
owns: docs/review-log/MONEY-SECURITY-LANE.md
serial_justified: |
  Money-path and security-path changes must be evaluated against ONE consistent picture of the
  live catalog and provider set. Split across tabs, two reviewers would reason about different
  snapshots of the same routing chain and could each approve a change the other's evidence
  refutes.
substrate: N/A
substrate-novel: |
  No tool is adopted or built. This is adversarial REVIEW and landing of existing money-path and
  security-path PRs. The mechanical half already exists and is used as-is: gh pr checks, the
  CHARON-GATE public-clean/bandit/gitleaks/semgrep legs, and the gateway's own /v1/models probe.
accept: |
  CRITICAL CODE — every item here gets an ADVERSARIAL review, per standing rule, and money-path
  changes are guilty until proven innocent.
  1. PR #212 PRICE-REFRESHER. This is the money-path CRITICAL PATH: the live catalog has only
     10 of 861 models priced, so cost ordering cannot work no matter how correct the sort. PR
     #207 was BOUNCED for exactly this — a strict no-op whose sort key is degenerate over an
     unpriced catalog, and which also claimed an unpriced leg "sorts last" when the 1000 sentinel
     equals a blended $10/M model, demoting PRICED legs below unpriced ones.
  2. PR #211 CATALOG-REFRESH-PERSIST is DRAFT and must stay draft until its known gap is closed:
     bind() snapshots static config into _base once at build_server, and bridge() rebuilds live
     routes from that snapshot every cycle, so a model an operator DISABLES after startup is
     RESTORED by the next bridge. Verify before landing.
  3. Consolidate the provider-key-exfil work: fix/provider-key-exfil, -interim, -v2,
     -v2-round5, -round6 are FIVE variants of ONE security fix, none with a PR. Pick the best on
     evidence, open its PR, close the rest with the reason. FIX-PROVIDER-KEY-EXFIL is now
     tier: frontier because it derives frontier on a security-critical path.
  4. Every claim of a safety property must be verified by grepping for the MECHANISM, and every
     suite must be run with the change REVERTED before it is believed. Two shapes accounted for
     6 of 8 bounces today: a safety property asserted only in prose, and a suite that passes
     against a mock of the component under test.

## Dependencies & Sequence

THIRD in blast radius but HIGHEST in consequence — this is the only lane touching money and
security. Runs concurrently with the other two (disjoint owns; different repo).

Internal order: (1) #212 PRICE-REFRESHER first, because cost ordering over an unpriced catalog
cannot work and everything else in the money path is downstream of pricing existing at all;
(2) #211 verify-then-land; (3) the five provider-key-exfil variants consolidated last, since
picking the best requires the catalog picture the first two establish.
