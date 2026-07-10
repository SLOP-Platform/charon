# Institutionalization Audit — manager memory → enforced homes

Date: 2026-07-08. Directive: stop keeping lessons in MEMORY (manager-scoped,
soft, doesn't reach droids / fresh sessions / the product). Institutionalize
each into the rig/repo/product/hooks where it is ENFORCED regardless of recall.
Memory shrinks to only what genuinely can't be mechanized.

**No memory deleted, no settings/hook files edited, no commits made.** This is
findings + exact recommendations only.

## Deliverables produced
- **BUILT:** `/home/stack/charon-private/fleet/MANAGER-OPERATING-RULES.md` — the durable committed home for all (a) BEHAVIOR/DOCTRINE rules, grouped Cadence / Presentation / Delegation / Execution / Review-Gates / Safety / Mindset. Each rule is one enforceable line with a `[memory-ref]`.
- This audit file.

## Counts per class
| Class | Meaning | Count |
|---|---|---|
| 🟢 (a) BEHAVIOR/DOCTRINE | how any session should WORK → doctrine doc + hook | 28 |
| 🟡 (b) RIG/PRODUCT FEATURE | rig gate/detector or product ticket | 5 |
| 🔵 (c) ALREADY MECHANIZED | demote to pointer / delete | 3 |
| ⚪ (d) GENUINE MEMORY | session-recall / project-state / who-owns / resolved-bug / hosting / design-of-record | 24 |
| | **Total memories** | **60** (+ MEMORY.md index) |

---

## SessionStart hook — where the standing reminder lives + how to wire the doc

**Source of the "MANAGER STANDING REMINDER":**
`/home/stack/code/charon/.claude/settings.local.json` → `hooks.SessionStart[0].hooks[0]` (lines 255–262). It is an inline `echo '...'` of a 3-point string (delegate / blast-radius / product-boundary), `statusMessage: "Manager standing reminder"`. That inline string is the ONLY thing every session currently loads — the other 57 rules never reach a fresh session.

**Recommended change (do NOT apply — operator confirms):** replace the inline `echo` with a `cat` of the committed doc so the FULL ruleset loads from the repo, not from a frozen string:

```json
"SessionStart": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "cat /home/stack/charon-private/fleet/MANAGER-OPERATING-RULES.md 2>/dev/null || echo 'MANAGER RULES DOC MISSING — see fleet/MANAGER-OPERATING-RULES.md'",
        "statusMessage": "Manager operating rules"
      }
    ]
  }
]
```

Notes:
- The doc is ~5 KB — fine to inject whole at SessionStart (one-time, not per-turn).
- Keep the fallback `echo` so a moved/renamed doc fails loud, not silent.
- `settings.local.json` is machine-local (not committed / not public) — correct place for a `/home/stack` absolute path; the DOC it points at lives in the private fleet repo. No public-repo leak.
- Alternative if you want it committed & portable: point the hook at a repo-relative path via `$CLAUDE_PROJECT_DIR`, but the fleet rig is a separate tree from charon, so the absolute path in the local settings is the pragmatic choice.

---

## MAPPING TABLE (memory → class → institutionalized home → action → demote?)

### 🟢 (a) BEHAVIOR/DOCTRINE → consolidated into MANAGER-OPERATING-RULES.md + hook

| Memory | Home (doc section) | Action | Demote memory? |
|---|---|---|---|
| work-in-phases-gather-then-wait | §1 Cadence | doc-built | y → pointer |
| pause-after-question-or-action | §1 Cadence | doc-built | y → pointer |
| discuss-before-acting-on-questions | §1 Cadence | doc-built | y → pointer |
| adversarial-review-must-not-silently-override-operator | §1 Cadence / §5 | doc-built | y → pointer |
| operator-prefers-simplest-tooling | §1 Cadence | doc-built | y → pointer |
| present-findings-in-color-tables | §2 Presentation | doc-built | y → pointer |
| remaining-work-includes-designed-not-built | §2 Presentation | doc-built | y → pointer |
| always-give-exact-command | §2 Presentation | doc-built | y → pointer |
| droid-launch-with-wait-retry-flags | §2 Presentation | doc-built (also fleet-droid.sh defaults) | y → pointer |
| manager-gives-new-session-prompt | §2 Presentation | doc-built | y → pointer |
| tl-terse-status-command | §2 Presentation | doc-built | y → pointer |
| manager-delegates-to-subsessions | §3 Delegation | doc-built (already in hook) | y → pointer |
| all-work-in-subsessions | §3 Delegation | doc-built | y → pointer |
| coordinator-token-economy-doctrine | §3 Delegation | doc-built; authoritative = COORDINATOR-DOCTRINE-v2.md | KEEP slim (rollout status pending) |
| manager-context-burn-control | §3/§4 | doc-built | y → pointer |
| subsession-model-and-token-policy | §3 Delegation | doc-built | y → pointer |
| recommend-model-for-droid-work | §3 Delegation | doc-built (refs MODEL-WORK-MATRIX.md) | y → pointer |
| droid-brief-final-commit-rule | §3 Delegation | doc-built (also BRIEF-TEMPLATE.md) | y → pointer |
| manager-never-spawns-droids | §3 Delegation | doc-built | y → pointer |
| dont-build-products-in-manager-session | §3 Delegation | doc-built | y → pointer |
| optimize-execution-wallclock-tokens | §4 Execution | doc-built | y → pointer |
| disjoint-owns-not-no-dependency | §4 Execution | doc-built | y → pointer |
| standing-blast-radius-lens | §5 Review-Gates | doc-built (already in hook) | y → pointer |
| adversarial-review-default-for-droid-prs | §5 Review-Gates | doc-built | y → pointer |
| never-ignore-preexisting-issues | §5 Review-Gates | doc-built | y → pointer |
| charon-build-methodology | §5 Review-Gates | doc-built | KEEP slim (ties to REVIEW-LOG process) |
| investigate-and-backup-before-data-loss | §6 Safety | doc-built | y → pointer |
| product-vs-build-rig-boundary | §6 Safety | doc-built (already in hook) | y → pointer |
| charon-production-readiness-mindset | §7 Mindset | doc-built | y → pointer |

### 🟡 (b) RIG/PRODUCT FEATURE → gate/detector or ticket

| Memory | Home | Action | Demote? |
|---|---|---|---|
| always-fix-catalog-mismatches | detection = ticket **#30** (exists); "fix on sight" doctrine in §? — add to doc if desired | already-ticketed-pointer | KEEP slim (points to #30) |
| use-free-tiers-to-their-limits | pools redesign + a **quota-tracking/spill mechanism** — NO existing ticket found | **ticket-to-file (NEW)** | KEEP (product directive) |
| multiple-tested-options-per-tier | pools redesign **#14** + real-outcomes benchmark **#26** | already-ticketed-pointer | KEEP (product directive) |
| charon-work-composition-intelligence | WCI tickets exist; product WCI parked per wci-rig-enforced-product-deferred | already-ticketed-pointer | KEEP (product feature) |
| charon-modular-agent-and-provider-agnostic | HARD product constraint — belongs in an **ADR + conformance test**; unclear if captured | **ticket-to-file (NEW: ADR/guard)** | KEEP (product constraint) |

### 🔵 (c) ALREADY MECHANIZED → demote

| Memory | Mechanism | Action | Demote? |
|---|---|---|---|
| ds-standing-rule | `validate_board.sh` (D&S enforced) | already-mechanized-pointer | y → pointer/delete |
| wci-ticket-decompose-method | `wci-contention.sh` (just landed) | already-mechanized-pointer | y → pointer/delete |
| public-repo-no-personal-info | public-clean gate + pre-commit hook (commits cfa3159 / 1c54ef4); doctrine also in doc §6 | already-mechanized-pointer | y → pointer |

### ⚪ (d) GENUINE MEMORY → keep as-is (can't be mechanized)

| Memory | Why it stays |
|---|---|
| charon-project-state | live session-recall / build state |
| charon-hosting-and-runner | hosting facts + collision guard |
| charon-vision-gateway-first | product vision |
| charon-repo-hygiene-audit | DONE record |
| charon-push-guard-gap | PARKED safety gap — **recommend operator-only settings fix** (see below) |
| charon-perf4-next-session | project next-step |
| droid-robot-mode-harness | reference artifact location |
| charon-build-via-fleet | rig-usage knowledge (which tooling to use) |
| charon-own-work-engine | design decision record |
| slop-tickets-location | who/where (tickets in mediastack tracking.db) |
| charon-portable-orchestration-store | design-only (obol) |
| charon-ci-runner-pattern | factual: how CI runner selection works (CI_RUNNER var) |
| charon-commandcode-plan-gate | parked provider decision |
| charon-deploy-drift-lessons | deploy runbook lessons (also RUNBOOK.md) |
| charon-failover-bug-and-tier-fallback | confirmed bug + want |
| charon-free-tier-routing | research doc pointer (FREE-TIER-ROUTING.md) |
| charon-silent-downgrade-leak | RESOLVED-bug record |
| rocinante-is-live-slop-prod | hosting / who-owns |
| durable-bridge-rework | active project state |
| fleet-rig-absolute-path | factual path |
| fleet-rig-grounding-docs | factual: where the rig files are |
| charon-pools-redesign | design-of-record (ADR-v2) |
| benchmark-not-a-valid-ranker | validity decision + pivot (design-of-record) |
| wci-rig-enforced-product-deferred | DECISION record (rig-enforced now / product parked) |

---

## (b) items with NO existing mechanism → RECOMMENDED tickets (not filed)

1. **Free-tier quota tracker + auto-spill** (`use-free-tiers-to-their-limits`): a balance-style tracker of each free-tier backend's daily/weekly/monthly remaining quota, consumed before paid, that auto-spills to the next backend on exhaustion (single-user ToS only). No ticket found. File against the pools-redesign capability engine.
2. **Provider/agent-agnostic conformance guard** (`charon-modular-agent-and-provider-agnostic`): an ADR capturing the HARD constraint + a test/detector that fails if the engine hardcodes a specific agent (opencode) or provider anywhere off the gateway abstraction. Verify no ADR already covers this before filing.
3. **(Safety, already parked) push-guard `git -C` bypass** (`charon-push-guard-gap`): the settings deny-list blocks `git push*` / `reset --hard*` but the `git -C <path>` form bypasses it. Operator-only settings fix. Not a new feature ticket — a settings hardening the operator must apply. See also `fleet/SETTINGS-GUARD-PROPOSAL.md`.

---

## DEMOTION LIST (recommend slim-to-pointer or delete — operator confirms; NOT deleted here)

Once MANAGER-OPERATING-RULES.md is wired into the hook, these become redundant
as full memories. Recommend slimming the body to a single pointer line:
`Institutionalized → fleet/MANAGER-OPERATING-RULES.md §<section>`.

**Slim to pointer (fully captured in the doc — 24 memories):**
work-in-phases-gather-then-wait, pause-after-question-or-action,
discuss-before-acting-on-questions, operator-prefers-simplest-tooling,
present-findings-in-color-tables, remaining-work-includes-designed-not-built,
always-give-exact-command, droid-launch-with-wait-retry-flags,
manager-gives-new-session-prompt, tl-terse-status-command,
manager-delegates-to-subsessions, all-work-in-subsessions,
manager-context-burn-control, subsession-model-and-token-policy,
recommend-model-for-droid-work, droid-brief-final-commit-rule,
manager-never-spawns-droids, dont-build-products-in-manager-session,
optimize-execution-wallclock-tokens, disjoint-owns-not-no-dependency,
adversarial-review-default-for-droid-prs, never-ignore-preexisting-issues,
investigate-and-backup-before-data-loss, charon-production-readiness-mindset.

**Slim to pointer — already mechanized (3 memories):**
ds-standing-rule (→ validate_board.sh), wci-ticket-decompose-method
(→ wci-contention.sh), public-repo-no-personal-info (→ public-clean gate + doc §6).

**Keep but note "also in doc" (don't fully strip — carry extra context):**
coordinator-token-economy-doctrine (rollout status + COORDINATOR-DOCTRINE-v2.md),
charon-build-methodology (REVIEW-LOG process),
standing-blast-radius-lens / product-vs-build-rig-boundary /
manager-delegates-to-subsessions (already in the current hook string — keep until
the hook is switched to `cat` the doc, then slim),
adversarial-review-must-not-silently-override-operator (operator-override nuance).

**Do NOT demote:** all 24 (d) genuine memories + the 5 (b) product directives
(they drive tickets/design, not session behavior).
