# REGISTRY-META-CATALOG — delta review of `78dd0c7` (adversarial, read-only)

**VERDICT: LAND-WITH-NITS**

Scope reviewed: **`78dd0c7` only** (`ad5fe51` was previously reviewed → LAND-WITH-NITS; not
re-reviewed here). Worktree `/home/stack/charon-private-wt/REGISTRY-META-CATALOG`, branch
`feat/registry-meta-catalog`, HEAD `78dd0c7`, tree clean.

Diff is **1 file, +2/-1, data-only**: `fleet/state/registry-catalog.tsv`. No script, no gate,
no test touched.

---

## Q1 — Are the two new/corrected rows CORRECT?

### Row: `lens-registry` (new) — `fleet/state/registry-catalog.tsv:33`

| field | declared | reality | verdict |
|---|---|---|---|
| `path` | `fleet/state/lens-registry.tsv` | file exists (added by master `aeb50ec`) | **OK** |
| `schema` | `lens\|goal\|linked_tickets\|status\|why` | header row `fleet/state/lens-registry.tsv:1` is exactly `lens⇥goal⇥linked_tickets⇥status⇥why` | **OK — exact** |
| `owner` | `LENS-REGISTRY-AND-REPORT` | ticket exists, `fleet/board/LENS-REGISTRY-AND-REPORT.md:7` `owns: fleet/state/lens-registry.tsv, ...` | **OK** |
| `conformance_gate` | `-` | independently verified: **no** `.sh`/`.py` in `fleet/` references the file. Its would-be gate `fleet/tests/lens-report.test.sh` (`LENS-REGISTRY-AND-REPORT.md:7`) has **not landed** — that ticket is still `ready`. | **OK — `-` is honest** |

Schema string also matches the ticket's own contract line `fleet/board/LENS-REGISTRY-AND-REPORT.md:20`.

### Row: `service-registry` (corrected) — `fleet/state/registry-catalog.tsv:26`

| field | declared | reality | verdict |
|---|---|---|---|
| `path` | `fleet/state/service-registry.tsv` | exists | **OK** |
| `conformance_gate` | `fleet/watchdog/discover-services.sh` | **exists**. The previously-declared `fleet/checks/service-liveness.sh` **does not exist** — the commit's claim checks out. | **OK — a real fix** |
| `schema` arity/order | 7 fields, `name,kind,alive_probe,freshness_probe,<ttl>,restart_cmd,owner` | real header `fleet/state/service-registry.tsv:32` = `name⇥kind⇥alive_probe⇥freshness_probe⇥freshness_ttl_s⇥restart_cmd⇥owner`; grammar `fleet/watchdog/watchdog-lib.sh:14` agrees; live data rows are 7-col (verified: `grader-daemon`, `session-bridge`) | arity + order **OK** |
| `schema` col 5 name | `ttl` | real name is **`freshness_ttl_s`** | **NIT — N1** |

**N1 (nit, factual):** the commit message says the schema was "Corrected to the real columns",
but column 5 is abbreviated `ttl` where the registry and the parser both call it
`freshness_ttl_s` (`fleet/state/service-registry.tsv:32`, `fleet/watchdog/watchdog-lib.sh:14`).
6 of 7 names are byte-exact; this one is not. The old row was wrong in arity *and* names, so
this is still a large net improvement — but a schema column that doesn't reproduce the real
header is the same class of latent drift the ticket exists to end. One-token fix.

---

## Q2 — Is the index COMPLETE?

**Complete for the contract that is actually ENFORCED. Not complete as "every registry in the rig".**

Independent repo-wide convention scan (run outside the gate, over the whole repo, not just
`fleet/`) finds exactly 6 convention-named registries, and **all 6 are catalogued**:

```
fleet/plane-canary-registry.tsv        OK
fleet/state/RULE-REGISTRY.tsv          OK
fleet/state/RULE-SYNC-REGISTER.tsv     OK
fleet/state/jedi-name-pool.txt         OK
fleet/state/lens-registry.tsv          OK   <- added by 78dd0c7
fleet/state/service-registry.tsv       OK
```

So `78dd0c7` is **not** a partial patch of a bigger set — for the enforced (convention) leg it is
exhaustive. Verified by execution: gate exits **0/GREEN** on HEAD.

**N2 (nit, pre-existing from `ad5fe51`, not introduced here) — the enforced set is narrower than
"every registry":**

- `fleet/checks/discover-registries.sh:71` scans `find "$FLEET" ...` — **only under `fleet/`**.
  A registry outside `fleet/` is structurally invisible to the fail-closed leg. (Today the repo
  has none, so this is latent, not live.)
- Non-convention registries are hand-seeded and the seeding is **selective**. Seeded:
  `tier-models.tsv`, `CONFIG-SOURCES.tsv`. Not seeded, though arguably registries by the same
  standard:
  - `fleet/config-manifest.tsv` — the config-SSOT git manifest
  - `fleet/state/EVAL-REGISTRY.md` — self-described "consult-first tool/library evaluation
    **registry**", has an explicit `## Schema` section (`fleet/state/EVAL-REGISTRY.md:1,14`)
  - `fleet/state/GATE-GAP-LEDGER.tsv`, `fleet/state/ON-DEMAND-TOOL-LEDGER.tsv`,
    `fleet/state/FREE-TIER-LIMITS.tsv`, `fleet/state/ROADMAP.tsv`

  None of these is a *regression* from `78dd0c7`, and each is a judgement call about what counts
  as a registry — but "one auto-discovered INDEX of **every** registry in the rig" is not yet
  literally true. Recommend a follow-up decision (either seed them, or write the exclusion rule
  into the catalog header so the boundary is declared rather than implicit).

---

## Q3 — Did the fix WEAKEN the gate? **No.** Proven by execution.

`git diff --name-only ad5fe51 78dd0c7` → `fleet/state/registry-catalog.tsv` **only**.
`git diff --stat ad5fe51 78dd0c7 -- fleet/checks/discover-registries.sh fleet/tests/registry-catalog.test.sh`
→ **empty**. The gate and its test are byte-identical to the already-reviewed commit. The row was
corrected; nothing was loosened.

Break/restore executed on a **scratch copy** (`REGISTRY_CATALOG_FLEET` seam), scratch since deleted;
worktree untouched (`git status` clean before and after):

| test | mutation | expected | **observed exit** |
|---|---|---|---|
| baseline | scratch copy, unmodified | GREEN | **0** |
| T1 fail-on-revert | delete the `lens-registry` row, file stays on disk | RED, names it | **1** — output named `fleet/state/lens-registry.tsv` |
| T2 stray registry | drop uncatalogued `bogus-registry.tsv` on disk | RED | **1** |
| T3 **wrong row data** | set `schema=totally\|wrong\|cols` + `conformance_gate=fleet/checks/DOES-NOT-EXIST.sh` | — | **0 (GREEN)** |
| T4 god-file creep | append a 7-column row | RED | **1** |
| shipped test suite | `bash fleet/tests/registry-catalog.test.sh` on HEAD | pass | **0** — `11 passed, 0 failed` |

The leg goes RED on genuinely missing/orphaned rows and on structural creep. It was **not** made
to pass by loosening.

**N3 (nit, pre-existing, and the strongest adversarial finding) — T3 is the real gap.**
The discovery leg reconciles **column 3 (`path`) membership only**
(`fleet/checks/discover-registries.sh:48,86-94`). It never validates `schema` (col 4) or
`conformance_gate` (col 6). That is exactly why the bogus `fleet/checks/service-liveness.sh`
pointer survived in the index until a human noticed — **no gate would ever have caught it**, and
no gate will catch N1 either. Cheap, in-scope follow-up for `discover-registries.sh`:

1. for every row with `conformance_gate != '-'`, assert the file exists → RED if not;
2. optionally assert col 4 equals the registry's own header/`# name...` line.

Not a blocker for this delta (it neither introduced nor worsened the gap), but it should be a
follow-up ticket — otherwise the catalog's non-path columns are unenforced prose.

---

## Q4 — Scope discipline: **clean.**

Single file, `fleet/state/registry-catalog.tsv`, which is the **first** entry in the ticket's
`owns` (`fleet/board/REGISTRY-META-CATALOG.md:7`:
`owns: fleet/state/registry-catalog.tsv, fleet/checks/discover-registries.sh, fleet/tests/registry-catalog.test.sh`).
Nothing outside `owns`. No drive-by edits, no unrelated hunks, no rebase artifacts.

## Q5 — 6-column index-only invariant: **intact.**

Both touched rows are exactly 6 tab-separated columns; every non-comment row in the file is 6
columns (structural guard `discover-registries.sh:53-61` passes; test B1 + F1 pass). No data
values from any catalogued registry leak into the index (test B2 passes). The added
`lens-registry` row carries only metadata/pointers — no lens rows. **No god-file creep.**

---

## Verified by EXECUTION vs by READING

**By execution:**
- discovery leg on HEAD → exit 0 / GREEN, 6/6 catalogued
- shipped test suite on HEAD → exit 0, 11 passed / 0 failed
- break/restore T1–T4 on a scratch copy → exits 1,1,0,1 as tabled above (scratch deleted)
- independent repo-wide `find` for convention-named registries (not reusing the gate's own scan)
- existence checks: `fleet/watchdog/discover-services.sh` **present**,
  `fleet/checks/service-liveness.sh` **absent**
- 7-column arity of live `service-registry.tsv` data rows via `awk NF`
- `git diff --name-only` / `--stat` for scope + gate-immutability

**By reading:**
- schema-name comparison against `fleet/state/service-registry.tsv:32` and
  `fleet/watchdog/watchdog-lib.sh:14` (found N1)
- `lens-registry.tsv:1` header vs the declared schema
- ticket `owns` sets in `fleet/board/REGISTRY-META-CATALOG.md:7` and
  `fleet/board/LENS-REGISTRY-AND-REPORT.md:7`
- judgement call on which non-convention `.tsv`/`.md` files qualify as registries (N2)

## Nits, in priority order

- **N3** — add `conformance_gate` file-existence assertion (and ideally schema-vs-header) to
  `discover-registries.sh`; the class of bug this commit fixed by hand is currently ungated.
  *Follow-up ticket, not a blocker.*
- **N1** — `service-registry` schema col 5: `ttl` → `freshness_ttl_s`. *One-token fix, land-time.*
- **N2** — decide and declare the boundary for non-convention registries
  (`config-manifest.tsv`, `EVAL-REGISTRY.md`, the ledgers) — seed them or document the exclusion.
  *Follow-up.*

Reviewer: agen-kolar · 2026-07-24 · read-only, worktree unmodified
