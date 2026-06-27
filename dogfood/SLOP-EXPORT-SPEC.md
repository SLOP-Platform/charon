# Work-spec: SLOP → Charon intake exporter (`slop_export.py`)

**Status:** Proposed (manager PREP; not built)
**Author:** manager research session, 2026-06-27
**Location of the thing to build:** `/home/stack/charon-private/dogfood/slop_export.py`
**Canonical tier:** `med` (mechanical stdlib script, single file) — fleet `sonnet`.

> ## ⚠ PRECONDITION — build + self-test against a CURRENT master checkout
> The build AND the self-test MUST run against a **current `master` checkout of charon**.
> The local `/home/stack/code/charon` is **28 commits behind on branch `docs/adr-0014`** and
> **LACKS `charon intake import`** (and the `id:` recognition this spec relies on). **Update it to
> `master` first** (`git -C /home/stack/code/charon fetch origin && git -C … checkout master &&
> git -C … pull`) **or use a fresh `master` worktree** — otherwise the §6 self-test will fail
> against a stale grammar and you will draw the wrong conclusion (this is exactly the staleness
> bug that produced the now-corrected §2 reconciliation below).

---

## 1. Purpose + the boundary rule

Turn SLOP's ticket store (`mediastack/tracking/tracking.db`) into a **markdown work-list
that the Charon `intake` parser accepts**, so the Charon build-fleet can DOGFOOD itself on
its own backlog. This is the dogfood enabler: SLOP's 33 open tickets → a Charon plan.

**Boundary rule (HARD — this is the whole point):**

- **OUT OF TREE.** The exporter lives under `/home/stack/charon-private/dogfood/`. It is
  **NOT** part of the Charon product and is **NEVER** added under `/home/stack/code/charon/src`.
- **The exporter is the ONLY thing that knows SLOP's schema.** No `tracking.db` / `backlog_items`
  / mediastack-specific knowledge may leak into `charon/src` — Charon's product side stays
  generic (it parses *markdown*, it does not know "SLOP"). Charon already enforces this:
  `tools/check_boundary.py` fails CI on any SLOP/tracking ref in `src/`.
- **Stdlib only, httpx-FREE.** Use `sqlite3` from the stdlib to read the DB. No `httpx`, no
  third-party deps, no Charon imports. It is a freestanding `python3` script.
- **Read-only on the product repos.** It reads `tracking.db` by *path* only. It writes exactly
  one output file (the plan) wherever `--out` points; default is under this dogfood dir.

---

## 2. Dependency note (read before building)

There are **two complementary pieces**, by design:

| Piece | Where | Status | Owns |
|---|---|---|---|
| `charon intake import` CLI + `id:` field recognition | `charon/src` (in-tree) | **BUILT — on `master`** (`_cmd_intake` cli.py ~915; `_ID_LABELS` intake.py ~53) | cli.py, intake.py |
| **this exporter** (`slop_export.py`) | `charon-private/dogfood` (out-of-tree) | this spec | the DB→markdown adapter |

> **CORRECTION (reconciliation #1 was wrong — authored against a STALE checkout).**
> An earlier draft of this section claimed there is "no `charon intake import` CLI" and that
> "`_apply_field` does NOT recognize an `id:` field." That was read off the local
> `/home/stack/code/charon` checkout, which is **28 commits behind on `docs/adr-0014`**. Both
> claims are **FALSE on `master`** — see the verified facts below.

Facts about Charon intake (verified 2026-06-27 against **`origin/master`**, not the stale local
branch — `git show origin/master:src/charon/{intake,cli}.py`):

- **`charon intake import <file>` CLI EXISTS on master.** `_cmd_intake` (cli.py ~915, "induct an
  external work-list into a reviewable plan"; subparser registered ~1193, `set_defaults(func=
  _cmd_intake)` ~1221) calls `intake.intake_file(...)` and writes a `charon-intake-plan` JSON.
  The Python API (`charon.intake.intake_file(path)` / `intake(text)`) still exists too.
- **intake HONORS an external-id field on master.** `_ID_LABELS = frozenset({"id", "ticket",
  "ticket_id"})` (intake.py ~53); `_apply_field` dispatches `elif label in _ID_LABELS:` (~166/176)
  and the id is **preserved through import to a board-safe slug** ("Preserve the source ticket's
  own id when supplied — load-bearing for the write-back/sink seam", ~512). So an emitted
  `id: slop-<id>` line is the **real** id-preservation mechanism — not a workaround.

**Therefore the exporter SHOULD emit a clean `id: slop-<id>` field per item** and rely on it for
id preservation. The heading-prefix trick is no longer needed as a preservation mechanism. See §4.

---

## 3. INPUT — read OPEN tickets from `tracking.db`

`tracking.db` is a SQLite file. The tickets table is **`backlog_items`**. Verified schema
(relevant columns):

```
backlog_items(
  id          INTEGER PRIMARY KEY AUTOINCREMENT,   -- the external SLOP id (e.g. 851)
  title       TEXT NOT NULL UNIQUE,                -- ticket title  -> heading / goal
  description TEXT,                                 -- ticket body   -> unit body (may be NULL/empty)
  status      TEXT NOT NULL DEFAULT 'open'          -- open|in_progress|done|parked|wont_fix
              CHECK (status IN ('open','in_progress','done','parked','wont_fix')),
  category, priority, tier, kind, batch, ...        -- extra metadata, NOT required by the exporter
)
```

**External id format:** a plain integer (`851`). It is referenced elsewhere in SLOP as `#851`.
Namespace it on export as **`slop-851`** (see §4) so it is self-describing and collision-free
against Charon's own title-slug ids, and so a future write-back can route completion to the
right source ticket.

**The OPEN-ticket query** (this is exactly how `query.py open` selects, minus presentation):

```sql
SELECT id, title, description
FROM   backlog_items
WHERE  status = 'open'
ORDER  BY id;
```

- As of 2026-06-27 this returns **33 rows** (memory said "~31"; it is now 33). 6 of those have a
  NULL/empty `description`.
- Default `--status` is `open`. (`query.py` itself only ever lists `status='open'` for "open".)
- **Do not** reuse `query.py`'s connection guards (pending-migration / decoy-DB checks). The
  exporter is a plain read: `sqlite3.connect(path)`, `row_factory = sqlite3.Row`, run the SELECT.
  Open read-only if you like: `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`.

---

## 4. OUTPUT — a Charon-intake-compatible markdown plan

### 4.1 The grammar Charon's intake parses (verified from `intake.py`)

`charon.intake.parse_markdown` (the only v1 adapter) reads a markdown work-item list:

- Each **`#`-heading** (outside a code fence) opens a work item; its **title** is the heading
  text and becomes the unit **`goal`**. The body runs to the next heading.
- A heading whose normalized title is an acceptance section name
  (`product acceptance`, `acceptance`, `done means`, `definition of done`,
  `acceptance criteria`, `product done`) is captured as the **top-level product acceptance**
  instead of a work item.
- Inside an item body, lines of the form **`label: value`** set fields. Recognized labels:
  - paths → `files | file | paths | path | owns | owned_paths`
  - acceptance → `accept | acceptance | test | tests | check | checks`
  - tier → `tier`
  - deps → `depends | depends_on | deps | on | after`
  - **id → `id | ticket | ticket_id`** (`_ID_LABELS`, intake.py ~53) ← preserves the external id;
    **recognized on master TODAY** and carried through import to a board-safe slug.
- **Fenced code blocks (```` ``` ````/`~~~`) are treated as DATA** — no headings/fields are
  parsed inside them (injection-safe).
- The unit **id** is `_make_id(title)`: lowercased, non-alphanumerics → `-`, **truncated to 48
  chars**, deduped. It must match `^[a-z0-9][a-z0-9-]{0,63}$` (`ledger.validate_task_id`).
- **An item with NO `accept:` becomes a propose-only `review_item` (kind `missing-acceptance`),
  kept OUT of the loadable `units` list.** An item with no paths AND no accept AND no body is
  dropped to a `need-more-detail` issue (never invented).

### 4.2 What the exporter emits (one item per OPEN ticket)

Emit a top-level acceptance section, then one heading per ticket. **Preserve the SLOP id with a
clean `id: slop-<id>` field** — that is the real, master-honored mechanism. The heading may carry
the title (optionally `SLOP-<id>: <title>`) purely as a **human-readable label**; it is no longer
load-bearing for id preservation.

```markdown
# SLOP backlog export (generated by dogfood/slop_export.py — do not hand-edit)

## Product acceptance
Each imported SLOP ticket is reviewed and enriched (accept + owns) before any run.
This export carries titles + descriptions only; it asserts no executable acceptance.

## BATCH-50 finding F: pytest-xdist -n auto …
id: slop-851
> Enable pytest-xdist -n auto parallelism to cut ~74% of CI wall-time after
> worker-isolation gaps are hardened — prerequisite: resolve recurring isolation
> failures first.

## Full backup product: retention, restore-test/verify, …
id: slop-868
> Extend the MVP local-config-volume tar backup to a full product covering …
```

**Id preservation — the `id:` field IS the mechanism (master):**
- **`id: slop-<id>` field** → recognized by `_ID_LABELS = {id, ticket, ticket_id}` (intake.py ~53)
  and preserved through import to a board-safe slug `slop-<id>`. This is load-bearing and works on
  current master. The exporter MUST emit exactly one `id: slop-<id>` line per ticket.
- The `slop-` namespace keeps it self-describing and collision-free against Charon's own
  title-slug ids, and lets a future write-back route completion to the right source ticket.
- **Optional human-readable heading prefix** `SLOP-<id>: <title>` is allowed as a *title* only;
  do **not** rely on `_make_id`'s heading slug for id recovery anymore — the `id:` field supersedes
  it. (If you keep the prefix, the `id:` field still wins as the unit's id.)

**Description handling (REQUIRED — injection/structure safety):** a raw description can contain
lines that start with `#` (parsed as a spurious new heading) or a ```` ``` ````/`~~~` fence
marker (toggles fence state and could swallow following tickets). **Neutralize every description
line by prefixing it with `> ` (blockquote):** `> #…` does not match the heading regex (`^#`)
and `> ```` does not match the fence regex (`^\s*```` ``` ````), so the body stays inert data and
never breaks item boundaries. Empty/NULL description → emit a single `> _(no description)_` line.

**No `accept:` / `owns:`.** The exporter deliberately emits neither. Per ADR-0011 that means
every ticket lands as a **propose-only `review_item` (missing-acceptance)** — which is correct:
the export is a faithful, un-enriched mirror of the backlog. The id + title + description are all
preserved on the review item.

### 4.3 Enrichment is a SEPARATE, post-import step (NOT the exporter's job)

Turning a review-item into a runnable unit (adding `accept:` = an executable check, and
`owns:`/paths) is **explicitly out of scope.** It is a human/manager step done *after* import,
on the plan, per ADR-0011's "human approves/edits before any run" posture. The spec for the
exporter ends at "faithful markdown mirror with ids preserved."

---

## 5. CLI

```
python3 slop_export.py [--db <path>] [--out <file>] [--status open]
```

- `--db`  default `/home/stack/code/mediastack/tracking/tracking.db`
- `--out` default `/home/stack/charon-private/dogfood/slop-backlog.plan.md`
- `--status` default `open` (the only value `query.py` exposes as a working set; allow it to be
  overridden for `done`/`parked`/etc. but keep `open` the default).
- Prints a one-line summary to stdout: `wrote N items (status=open) -> <out>`.
- Pure stdlib: `argparse`, `sqlite3`, `pathlib`. **No `httpx`, no `charon` import.**

---

## 6. SELF-TEST (the build session must run this and show it green)

> Runs against a **current `master` checkout** (see PRECONDITION). The stale local
> `docs/adr-0014` checkout has no `intake import` and will fail step 2.

1. **Generate:** `python3 slop_export.py --out /tmp/slop.plan.md` → exits 0, prints `wrote 33 …`
   (accept ~31–35; the count must equal the independent
   `SELECT COUNT(*) FROM backlog_items WHERE status='open'`).
2. **Parse via the REAL Charon CLI (primary):**
   ```bash
   charon intake import /tmp/slop.plan.md --out /tmp/slop.plan.json
   python3 -c "import json; p = json.load(open('/tmp/slop.plan.json')); \
     items = p.get('units', []) + p.get('review_items', []); print('parsed', len(items)); \
     assert len(items) == 33, len(items); \
     ids = [i['id'] for i in items]; \
     assert all(i.startswith('slop-') for i in ids), [i for i in ids if not i.startswith('slop-')]; \
     print('ids ok:', ids[:3])"
   ```
   - **Assert ~33 items parsed** (`units + review_items`), and **every item preserves its
     `slop-<id>` id** (via the honored `id:` field). With no `accept:`, expect these to be
     `review_items` (missing-acceptance), not loadable `units` — that is correct.
3. **Python-API path (secondary cross-check only):**
   ```bash
   python3 -c "from charon import intake; p = intake.intake_file('/tmp/slop.plan.md'); \
     items = list(p.units) + list(p.review_items); \
     assert len(items) == 33, len(items); \
     assert all(i.id.startswith('slop-') for i in items), 'id not preserved'; \
     print('api ids ok:', [i.id for i in items][:3])"
   ```
4. **No httpx:** `! grep -q 'import httpx\|from httpx' slop_export.py` (and the script imports no
   `charon`).
5. **No product-tree write:** assert the run wrote nothing under `/home/stack/code/charon/src`
   and nothing under `/home/stack/code/mediastack` (output went only to `--out`).
6. **Injection-as-data sanity:** a ticket whose description contains a `#`-line or a ```` ``` ````
   fence must NOT create extra items — parsed item count stays == open-ticket count.

---

## 7. Constraints recap (for the build session)

- Own ONLY `/home/stack/charon-private/dogfood/slop_export.py` (+ optionally a sibling
  `test_slop_export.py` in the same dir). **Do NOT touch `/home/stack/code/charon/src` or
  `/home/stack/code/mediastack`.**
- Stdlib only; `sqlite3` for the DB; httpx-free; no `charon` import.
- Read-only on `tracking.db`. One output file only.
- The `charon intake import` CLI is **already on master** — the self-test uses it as the primary
  parse path; the Python API is a secondary cross-check. Run against a current master checkout
  (see PRECONDITION). Do **not** add or modify any in-tree CLI from this ticket.
```
