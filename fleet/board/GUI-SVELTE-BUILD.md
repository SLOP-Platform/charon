tier: opus
branch: feat/gui-svelte-build
depends_on:
owns: src/charon/proxy_server.py, src/charon/config.py, src/charon/spend_limits.py, src/charon/gateway.py, gui/ (new Svelte/Vite project), pyproject.toml, Dockerfile, tests/test_proxy_server.py, tests/test_gui_*.py (new)
accept: PYTHONPATH=src python3 -m pytest -q tests/test_gui_endpoints.py tests/test_proxy_server.py && (cd gui && npm ci && npm run build)
prompt: /home/stack/charon-private/prompts/gui-svelte-build.md
scope: Replace the three inline-Python-string HTML consoles (_CONSOLE_HTML/_SETUP_HTML/
  _WORK_HTML in src/charon/proxy_server.py) with a static Svelte app, compiled via Vite,
  served SAME-ORIGIN by Charon's existing stdlib http.server (no new runtime dependency,
  no CDN, no framework at request-time — only at build-time). Light theme (operator
  preference); pi-hive is a visual reference only. Bearer-token auth (existing
  Authorization: Bearer / ?token=) is sufficient for v1 — the hardened signed-session-
  cookie design (AUTH-GUI-DESIGN.md, ticket GUI-AUTH-1) is a LATER phase, not a
  prerequisite. Investigation basis: GUI-API-SURFACE.md (2026-07-05) confirms the
  existing /charon/* JSON API covers full CRUD for providers/models/pools/tiers-write/
  fallback + usage/failover/cooldown observability, with exactly 2 read-side gaps to
  close first (tier config read-back; spend-cap view+set) — see Phase 0.
note: PRODUCT-LEVEL GUI rebuild. Ships standalone in the public repo — NO fleet/SLOP/
  runner dependency may leak in (product-vs-build-rig boundary). The Vite/Node build
  step is a BUILD-TIME-ONLY tool (like pyinstaller in packaging extras) — it must NOT
  become a runtime dependency of the installed package or the Docker image's `pip
  install '.[service]'` path, and must not break the existing pip/pipx/curl install or
  the Mode-B service profile. Compiled gui/dist output ships as packaged static assets
  (wheel package_data), NOT built inside the Docker image or at pip-install time.

## Phased build scope

### Phase 0 — API gaps (S)
Goal: close the 2 read-side gaps GUI-API-SURFACE.md found, so every panel in Phase 2
has a real endpoint to bind to before any Svelte code is written.
- Files: `src/charon/config.py` (`summary()`), `src/charon/proxy_server.py`
  (`status_snapshot()`, `make_setup_handler()` dispatch), `src/charon/spend_limits.py`
  (expose `remaining()` + configured `_limit_usd` via a getter), tests.
- Deliverables:
  1. `config.summary()` gains a `tiers` key sourced from `load_tiers()` (order, members,
     aliases) — makes the existing write-only Tiers panel round-trip.
  2. `status_snapshot()` gains `spend_limit` (configured monthly ceiling) and
     `spend_remaining` (from `SpendLimiter.remaining()`); new `POST /charon/spend-limit`
     write action wired into `make_setup_handler()`'s dispatch (same CSRF/Origin guard
     as the other POST routes) so the cap can be viewed/changed without a restart.
- Effort: **S**. No new files besides tests; two small, additive JSON-shape changes
  plus one POST route following an existing pattern.
- D&S: no dependency; can build/merge before or in parallel with Phase 1 (disjoint
  from `gui/` files), but Phase 2 panels for Tiers/Spend-cap need it merged first.

### Phase 1 — build+serve skeleton (M)
Goal: prove the whole path end-to-end — one static Svelte panel, built by Vite,
served same-origin by Charon's existing stdlib handler, authenticated with the
existing bearer token — before building out all panels.
- New `gui/` project: Svelte + Vite, light theme, no CSS framework/CDN (keep the
  "zero external assets" security property GUI-API-SURFACE/AUTH-GUI-DESIGN both rely
  on for a tiny XSS surface). `npm run build` emits a static `dist/` (hashed
  filenames, relative asset paths — no absolute `/` root assumption issues since it's
  served from `/charon/`).
- Charon-side wiring in `proxy_server.py`: a new static-asset dispatch branch
  (e.g. `GET /charon/app/*` or repoint `/charon`, `/charon/setup`, `/charon/work` to
  serve the compiled `index.html`/hashed JS/CSS from a packaged assets dir) alongside
  the existing token gate — reuse `_authorized()` unchanged, no new auth surface in
  this phase. Decide and document: single-page-app (client-side router, one
  `index.html` for all `/charon/*` GUI routes) vs. keeping the 3 separate served
  pages — recommend SPA to match "one bundle, client router" Svelte idiom.
  fetch() calls attach `Authorization: Bearer <token>` (token entered once, held in
  the SPA, e.g. sessionStorage) exactly per GUI-API-SURFACE.md's "works NOW" auth note.
- Packaging: wire `gui/dist` into the Python package as `package_data` (hatchling
  `[tool.hatch.build.targets.wheel]` — add a `force-include` or artifacts entry) so
  `pip install` ships the compiled assets without requiring Node at install time.
  Dockerfile: decide where the Vite build runs — recommended: a CI/release build
  step that runs `npm ci && npm run build` and commits/publishes `gui/dist` as a
  build artifact BEFORE `docker build`, so the image's `pip install '.[service]'`
  stays Node-free (no new build stage, no image bloat, keeps the "stdlib-only
  privileged path" invariant intact for the parts that matter — this is a UI build
  tool, not privileged-loop code, but the image should still not need to install
  Node to produce a working container).
- One working panel end-to-end (recommend: Providers list, since it's the simplest
  read+one write (`GET /charon/config` → table; `POST /charon/providers` → add) to
  validate the full auth+CSRF+build+serve chain before investing in 5 more panels.
- Effort: **M**. This phase is the actual unknown/risk (build tooling, packaging,
  same-origin serving from stdlib http.server) — everything after it is repetitive.
- D&S: depends on nothing structurally, but doing it AFTER Phase 0 merges means the
  one proof panel can optionally exercise the new tiers/spend-limit shapes instead of
  needing a second wiring pass later. Single writer on `proxy_server.py` dispatch —
  no other ticket should be editing that file concurrently (note the existing
  CONSOLE-PROVIDER-MGMT ticket's own "SERIALIZE... both own proxy_server.py" warning;
  re-check board state before claiming).

### Phase 2 — panels (M/L, likely splittable per-panel)
Goal: build out every dashboard panel against its concrete existing endpoint(s),
replacing `_CONSOLE_HTML` (dashboard), `_SETUP_HTML` (config forms), `_WORK_HTML`
(orchestrator runs) in full.
Panel → endpoint map (from GUI-API-SURFACE.md §1-2):
- **Providers** (list/add/edit/remove) → `GET /charon/config` (`providers`),
  `POST /charon/providers`, `POST /charon/remove {kind:"provider"}`.
- **Models** (list/add/edit/import/enable/disable/remove) → `GET /charon/config`
  (`models`), `POST /charon/models`, `POST /charon/models/import`,
  `POST /charon/enable` / `/disable`, `POST /charon/remove {kind:"model"}`.
- **Pools** (list/view/add/edit + reorder) → `GET /charon/config` (`pools`) +
  `GET /charon/status` (`pools`, live chain) for display; `POST /charon/pools` for
  create/edit (reorder = re-POST the full ordered member list — no dedicated reorder
  endpoint exists; confirm this is acceptable or flag as a 3rd gap).
- **Tiers** (view + set order/members/aliases) → `GET /charon/config` (`tiers`, from
  Phase 0) + `POST /charon/tiers`.
- **Fallback** (global fallback provider order) → `GET /charon/config` (`fallback`,
  `fallback_pricing`) + `POST /charon/fallback`.
- **Metrics/spend** (cumulative usage, cost, spend cap+remaining) →
  `GET /charon/status` (`usage`, from Phase 0: `spend_limit`/`spend_remaining`) +
  `POST /charon/spend-limit` (from Phase 0).
- **Failover/health** (recent failovers feed, per-provider cooldown/served/failed) →
  `GET /charon/status` (`recent_failovers`, `cooldown_seconds`, `providers`).
- **Work/obs** (orchestrator work-unit runs) → `GET /charon/work?json=1`
  (`console_work.gather_runs()`).
- Further gaps called out during Phase 2 (not yet built, flag if hit): pool-member
  reorder as a first-class action (see Pools above); no per-provider real account
  balance (GUI-API-SURFACE explicitly scopes this OUT); RFL-1 quota tracker
  (`quota.py`) is not wired to any endpoint yet — out of scope here unless a future
  ticket wires it into `status_snapshot()`.
- Effort: **L** overall; each bullet above is independently a small panel once Phase 1's
  skeleton exists — can be split into per-panel sub-tasks/waves if parallelizing.
- D&S: depends on Phase 1 (skeleton+auth+build pipeline) and Phase 0 (tiers/spend
  shapes) both merged. Panels are disjoint from each other in the `gui/` tree (separate
  Svelte components) so can parallelize across sub-sessions once Phase 1 lands, but
  ALL still share `proxy_server.py` dispatch if any panel needs a new/adjusted
  endpoint — flag and serialize those specific edits.

### Phase 3 — hardened auth (M)
Goal: implement GUI-AUTH-1 per AUTH-GUI-DESIGN.md — signed `charon_sess` session
cookie + `/charon/login` + `/charon/logout`, replacing the bearer-token-in-JS-state
posture from Phase 1 as the DEFAULT (token remains a valid fallback per the design's
non-negotiable invariant: `/v1/*` untouched).
- Files (from AUTH-GUI-DESIGN.md §8 "Owns"): `proxy_server.py` (`_LOGIN_HTML`,
  `_valid_session()`, `_issue_session()`/`_clear_session()`, surface-aware dispatch),
  `secrets.py` (`get_or_create()`), `gateway.py` (session-key generation + banner),
  `cli.py` (`charon login`, `charon logout --all`), new
  `tests/test_gateway_gui_auth.py`, docs.
- Deliverables: full 10-point acceptance criteria + test plan already specified in
  AUTH-GUI-DESIGN.md §8 — this ticket just executes that ticket-ready spec against
  the now-Svelte GUI (the Svelte SPA swaps its token-in-storage fetch wrapper for
  cookie-based fetch with no explicit Authorization header once logged in).
- Effort: **M**. Design is already fully specified (AUTH-GUI-DESIGN.md is DTC'd); this
  is implementation + the existing test plan, not new design work.
- D&S: depends on Phase 1 (there must be a Svelte SPA whose fetch wrapper this
  changes) but is otherwise independent of Phase 2's panel count — can start once
  Phase 1 merges, in parallel with Phase 2, IF `proxy_server.py` dispatch edits are
  coordinated (single-writer rule) with any Phase-2 endpoint work landing at the same
  time. Recommend sequencing Phase 3 AFTER Phase 2 to avoid two concurrent writers on
  the same dispatch function, unless board state shows Phase 2 is fully idle.

## Cross-cutting notes

- **Product boundary:** everything under `gui/` and the packaged `dist/` ships in the
  PUBLIC repo standalone — no reference to fleet/SLOP/the runner/`/home/stack` paths
  anywhere in the Svelte source, build config, or docs (per public-repo-no-personal-
  info). The Vite/Node toolchain is a build-time-only dependency (like the `packaging`
  extra's pyinstaller) — must never appear in `dependencies` or `service` extras, and
  the Docker image's runtime `pip install '.[service]'` step must stay Node-free.
- **Light theme + accessibility:** current inline GUI is dark (`#0b0e14`); the Svelte
  rebuild flips to light per operator preference, using pi-hive only as a rough visual
  cue (spacing/table density), not its component library or dark palette. Carry
  forward basic accessibility hygiene the inline HTML currently lacks explicitly:
  sufficient contrast ratios for a light theme, visible focus states on
  buttons/inputs, semantic HTML (real `<table>`/`<label>` elements, not div soup) —
  cheap to get right from scratch, expensive to retrofit later.
- **Risks / open questions:**
  1. **Biggest risk:** packaging the compiled `gui/dist` into the wheel/Docker image
     without adding Node as a runtime or CI-install-time dependency for end users who
     `pip install charon` from source (vs. a pre-built wheel/sdist) — if the sdist
     doesn't ship pre-built `dist/` assets, a from-source pip install would need Node
     to produce a working GUI, which breaks the "no host Python/Node barrier" fresh-
     install goal DOCKER-INSTALL.md already fought to remove. Must decide: ship
     compiled assets IN the sdist/wheel (checked-in build artifact refreshed by CI) vs.
     require Node at install time (reject — contradicts fresh-install goals).
  2. `proxy_server.py` is a hot file across multiple in-flight/recent tickets
     (CONSOLE-PROVIDER-MGMT, RFL-1, this ticket's own Phase 0/1/3) — owns-collision
     re-check required at claim time for whichever phase claims first.
  3. Pools reorder: no dedicated reorder endpoint exists (Phase 2 flags this) — decide
     if re-POSTing the full pool is acceptable UX or needs a 3rd small endpoint.
  4. SPA vs. multi-page serving model (Phase 1 decision) affects whether `/charon`,
     `/charon/setup`, `/charon/work` become one client-routed app or stay three
     separately served entry points — pick one before Phase 2 panel work starts, to
     avoid rework.
  5. Bundle size / no-CDN constraint: Svelte compiles small by default, but confirm no
     panel pulls in a heavy chart/table library that violates the "zero external
     assets, tiny XSS surface" property AUTH-GUI-DESIGN.md's threat model leans on.
