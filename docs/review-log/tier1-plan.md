## 2026-06-23 — Tier 1 build plan (ADR-0001/0002/0003)

- **Change under review:** `docs/PLAN-tier1.md` — initial standalone repo + the
  continuity core (Ledger, fence, ports, coordinator) before any code.
- **Reviewers:** two independent read-only adversarial subagents (Opus),
  dispatched in parallel — lens A = blast-radius, lens B = out-of-the-box /
  premise-attack. Each derived risks independently from the three ADRs, then
  attacked the plan.
- **Charge (fixed, author could not soften):** find what will hurt; where the
  privileged loop escapes the fence; how the ledger corrupts; supply-chain holes;
  whether the core premise (cross-vendor handoff) is even the valuable problem;
  whether ACP is a safe bet; what to validate BEFORE writing code.

### Findings + reconciliation

| ID | Finding (sev) | Verdict | Reconciliation |
|----|----|----|----|
| BR-1 | Ledger JSON not crash-safe; concurrent coordinators corrupt silently (CRIT) | **ACCEPT** | Atomic write via `tempfile`+`os.replace`; checkpoints are append-only JSONL (one record/line, partial trailing line skipped); per-task lockfile (PID+mtime, stale after TTL); malformed read → raise LOUD, never silent. `schema_version` field from first commit. |
| BR-2 | Fence is a Python predicate, not OS isolation; agent can `cd ..`, poison global git, `LD_PRELOAD` (CRIT) | **ACCEPT, re-scoped** | Tier 1 default autonomy = **L0 propose-only** (nothing applied). L1 apply is guarded: minimal scrubbed env (`env -i`-style: only PATH/HOME=worktree/TERM/CHARON_*), `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_SYSTEM=/dev/null`; post-run escape scan (any path mtime-touched outside the worktree ⇒ run rejected, not applied). True OS isolation is delegated to the **Mode B container** (ADR-0002 §2.3) — the doc does NOT claim a proven structural fence vs a live skip-perms agent in Tier 1. Honesty register updated. |
| BR-3 | Unvetted gateway enters the privileged loop (CRIT) | **ACCEPT** | Tier 1 ships **no network gateway**: routing = static policy file on disk, hard-pinned model ids. Gateway is Tier 2+, optional, gated on a `SUPPLY-CHAIN.md` audit. `pip-audit` runs in CI; runtime deps pinned and minimal (stdlib-first). |
| BR-4 | CI grep for the host-project package name trivially bypassed; a transitive `ms-router` dep could import the host project (HIGH) | **ACCEPT** | Boundary check is an **AST import scan** (`ast.walk`, catches `import`, `from`, `__import__("...")` literals), not a grep. Runtime guard: asserts the host-project package is not in `sys.modules` at startup. No `ms-router` dependency — routing is native/static, so no transitive host-project import path exists. |
| BR-5 | "No prose acceptance" is policy, not enforced (HIGH) | **ACCEPT, structural** | There is no prose field by construction: an acceptance criterion is `{id, cmd}` and `verified` ⇔ `cmd` exits 0. Prose passed as `--accept` is *run as a command*, fails to exit 0, so it can never become falsely "done" — it surfaces as loud, permanent incompletion. A constructor warning nudges the user. |
| BR-6 | Mock-only proof never exercises the privileged path = theater (HIGH) | **ACCEPT** | MockBackend gains **adversarial modes**: emit an incomplete ledger entry, attempt a worktree escape, try to advance `lkg_ref` past an unverified commit. Tests assert the coordinator/ledger **reject** each loudly (proven-red), so the invariants are tested, not just asserted. |
| BR-7 | Install blast radius (curl\|bash, privileged container) unmitigated (MED) | **ACCEPT, docs** | `install.sh` prints a prominent warning (spawns CLI agents / autonomous loop; not for shared machines); README is honest; unattended/L2+ is steered to the Mode B container. GPG/SLSA signing tracked for a later tier. |
| BR-8 | Two `charon run` on one task race (MED) | **ACCEPT** | Covered by the BR-1 lockfile. |
| OOB-C1 | Is cross-vendor handoff even the valuable problem? Possibly over-built vs cross-session resume (FUNDAMENTAL) | **ACCEPT, sequencing** | Tier 1 re-scoped to a **single-backend disciplined loop + Ledger** (which is what ADR-0001/0002 Tier 1 already says). The `AgentBackend` *port* stays (cheap seam, mandated by ports-and-adapters); the handoff H-predicate logic is built + unit-tested vs mock; **live cross-vendor handoff is Tier 2**, built only if the data justifies it. |
| OOB-C2 | ACP maturity unproven; H4 fidelity unvalidated; Tier 0 should precede coordinator code (CRIT) | **ACCEPT, made runnable** | Instead of deferring Tier 0 to "later," ship it as a command: **`charon doctor`** probes a present ACP backend for usage-reporting + resume/fork fidelity and reports gaps. Mock proves the loop; `doctor` grounds the real-backend assumptions on demand. The doc does not claim H4 is validated until `doctor` is run green against a real agent. |
| OOB-C3 | Executable-acceptance ⇒ this is a test-driven task runner, not a general agent (HIGH) | **ACCEPT** | Disclosed as a headline scope statement in README ("Charon runs goals with executable acceptance; prose-only goals are out of scope"). Framed as a deliberate narrowing, not a hidden limitation. |
| OOB-C4 | A ~500-LOC bash script gets 80% of the value (MED) | **REJECT as deliverable, accept as discipline** | The requirement is an installable, versioned, host-embeddable package with three public surfaces — bash is none of those. But the lesson lands: Tier 1 stays genuinely thin, git is the source of truth for `lkg_ref`, no formalism beyond what a public API needs. |
| OOB-C5 | "Charon" collides with Plan 9 / NASA tooling (LOW) | **ACKNOWLEDGE** | Operator-chosen; `SLOP-Platform/charon` namespace is clear; non-blocking. |
| OOB-C6 | ADRs missed: ledger schema-versioning hell; adapter-incompatibility creep | **ACCEPT** | `schema_version` + migrate-on-load from first commit; adapter incompatibility named as a watched class in the honesty register. |
| OOB-C7 | Frontier models may absorb this in months (existential) | **ACCEPT, docs** | README sunset clause: Charon is a tactical bridge; the Ledger is git+JSON and outlives Charon's removal. |

### Net effect on the build (folded into PLAN-tier1 §"Reconciled scope")
1. Ledger: atomic + JSONL checkpoints + lockfile + schema_version + loud-on-corrupt.
2. Fence: L0 default; L1 guarded (scrubbed env + escape scan); OS isolation = Mode B container.
3. No gateway in Tier 1 (static routing policy); `pip-audit` in CI.
4. AST boundary check + runtime host-project import guard; no `ms-router` dep.
5. Adversarial MockBackend modes; coordinator/ledger must reject them (proven-red).
6. `charon doctor` as the runnable Tier-0 backend probe.
7. README discloses: autonomous privileged loop, test-driven scope, sunset clause.

No WALK-BACK-LOG entry required: new repo, all additions/strengthenings.
