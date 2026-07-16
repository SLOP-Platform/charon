# FORWARDER-RECONCILE — review/decision log

Ticket: FORWARDER-RECONCILE (money-path, tier strong, depends_on FAIL-LOUD-CONTRACT)
Branch: `feat/forwarder-reconcile`. Supersedes the untracked branch
`feat/wire-tool-repair` (commit `af8d795`) per fleet/state/TOOL-AUDIT-COLLISION.md
RANK 1.

## Precondition confirmed

FAIL-LOUD-CONTRACT landed to master first: PR #151 merged as `166eb73`
(commit `c4377f7`, "feat(forwarder): structured providers_tried envelope on
terminal exhaustion"). Its structured `providers_tried` terminal-error contract
is live in `forward_with_failover()` on the master this branch is cut from —
verified by grep (`providers_tried`, `_REARM_FOR_CLASS` derivative logic at
forwarder.py:661–682) before any edit.

## What was merged, hunk by hunk (no autoresolve — both diffs read in full)

Source diffs read before touching code:
- `git show c472fee -- src/charon/forwarder.py` (FAIL-LOUD-CONTRACT, 3 hunks)
- `git show af8d795 -- src/charon/forwarder.py` (wire-tool-repair, 2 hunks)

### c472fee (FAIL-LOUD-CONTRACT) — ALL hunks already on master, UNCHANGED here
| hunk | content | status in merged file |
|---|---|---|
| `@@ -42,6 +42,15` | `_REARM_FOR_CLASS` map | on master (evolved by merge `c4377f7`), untouched by this branch |
| `@@ -405,6 +414,13` | `_cc_map` cost-class lookup | on master, untouched |
| `@@ -470,12 +486,28` | `providers_tried` 503 envelope + `retry_after_s` hint | on master (forwarder.py:661–689), untouched |

This branch adds ZERO lines inside the terminal-error/4xx-relay region — the
structured fail-loud contract is preserved byte-for-byte (`git diff master...HEAD`
shows no hunk overlapping it).

### af8d795 (wire-tool-repair) — forwarder.py hunks re-applied on top
| hunk | content | disposition |
|---|---|---|
| `@@ -92,6 +92,53` | `_tool_schemas_from_request` + `_repair_tool_call_response` helpers | applied verbatim after `_normalize_message_content` |
| `@@ -507,6 +554,13` | non-stream-200 call site: repair BEFORE `observed = _extract(...)` / classify/cache/serve | applied at the same anchor (after adapter `normalize_response`, before `_extract`), with ONE deliberate adaptation below |

**Deliberate adaptation (not a drop):** af8d795 read `srv.tool_repair` as a
direct attribute, which required its proxy_server.py change (constructor kwarg +
default-None attr). This branch reads `getattr(srv, "tool_repair", None)`
instead — the established pattern for optional server attrs (see proxy_server.py
"R3: optional capability deny-table ... forwarder reads via getattr" comment).
Behavior is identical: unset → guaranteed no-op, byte-identical body.

### af8d795 hunks NOT in this branch — deliberate, documented, out of `owns:`

This ticket's `owns:` is exactly `src/charon/forwarder.py`,
`tests/test_forwarder_fail_loud.py`, `tests/test_forwarder_tool_repair.py`.
af8d795 also touched two files this ticket does NOT own (both are owned by
other live board tickets — gateway.py by FT-WIRE-QUOTA and
PRICING-LIMITS-CHECKER):

1. **proxy_server.py** (kwarg + `_mod_param_names` + default attr): **now
   unnecessary.** Master's F29 registry grew a generic new-spec loop since
   af8d795's base (proxy_server.py:583–586: any extra `modules=` key is set as
   an attribute). `modules={"tool_repair": ToolCallRepair()}` reaches
   `srv.tool_repair` with zero proxy_server changes; the ported test was
   updated to inject via `modules=` accordingly. No behavior lost.
2. **gateway.py** (always-on `ModuleSpec("tool_repair", "tool_repair", ...)`):
   **still needed for the production gateway to enable repair by default**, but
   it is a 7-line disjoint hunk in a file owned by other tickets. Landing it
   here would double-claim. Follow-up needed (one-line ModuleSpec addition to
   `_MODULE_SPECS`, plus the ToolCallRepair import) — suggest folding into
   FT-WIRE-QUOTA (already owns gateway.py + forwarder.py) or a trivial
   GATEWAY-TOOL-REPAIR-SPEC ticket. Until then the seam is live and tested;
   the forwarder side is complete and any `modules=`-injected instance works.

This is the loud, recorded version of the drop — not silent. The
`forward_with_failover()` hunk-representation requirement in the accept
criteria is fully met (both source commits' forwarder hunks represented).

## Verification

- `PYTHONPATH=src python3 -m pytest tests/test_forwarder_fail_loud.py
  tests/test_forwarder_tool_repair.py -q` → 9 passed (both suites, ONE forwarder.py).
- Full suite: 1827 passed, 1 xfailed, 1 xpassed.
- `PYTHONPATH=src python3 -m charon.cli gate` → CHARON-GATE: all checks passed.
- `ruff check` on owned files → clean. `mypy src tests` → clean.
  (Repo-wide `ruff check` has 5 pre-existing failures in
  `tools/_vendor/ksf_inert_code.py` present on unmodified master — verified via
  `git stash` A/B — outside this ticket's owns; gate is nonetheless GREEN.)
- **Fail-on-revert re-verified in THIS worktree:** forcing the call-site guard
  to `None` makes `test_malformed_tool_call_repaired_end_to_end` RED
  (JSONDecodeError on the served malformed arguments); restoring it → GREEN.

## Branch retirement (post-merge operator step)

`feat/wire-tool-repair` (worktree
`$CHARON_MAIN/.claude/worktrees/agent-a4294af67f9d41d80`, commit
`af8d795`) is superseded by this branch. It must be retired AFTER
`feat/forwarder-reconcile` merges (deleting it earlier would destroy the only
copy of the source work if this PR were rejected):

```
git -C "$CHARON_MAIN" worktree remove --force \
  "$CHARON_MAIN/.claude/worktrees/agent-a4294af67f9d41d80"
git -C "$CHARON_MAIN" branch -D feat/wire-tool-repair
```

This droid session did not run these (they mutate the main checkout, which is
off-limits to worker sessions).
