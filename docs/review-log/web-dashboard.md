## 2026-06-25 — Read-only web Ledger dashboard (ADR-0004 D7/R3)

- **Change under review:** the MVP web frontend — a minimal, read-only,
  token-gated, single-operator Ledger dashboard served by the existing
  (read-only, 501-on-runs) `service/app.py`. New: `api.list_ledgers` /
  `api.show_config` (read-only helpers), `/v1/runs` (list) + `/v1/config` + `/`
  (self-contained HTML) routes, a `require_token` gate, and `python -m
  charon.service` with a non-loopback bind guard. The privileged loop stays out
  of the web process (ADR-0002 §2.3 / INV-B4) — `POST /v1/runs` still refuses
  (501); the enqueue→worker run path remains deferred to Tier 2b with its
  Tier-3 host-project consumer (R3). Deferred-and-NOT-built (per R3): web config/pool
  CRUD, live streaming, stage-graph viz, multi-workspace.
- **Process:** one focused read-only adversarial subagent (the methodology's
  low-impact tier — the architecture was already settled by ADR-0004 D7/R3 +
  the Tier-2b DTC, so this reviews the *implementation*, not a fork). Charge:
  boundary leaks, secret exposure, token-gate soundness, dashboard XSS,
  read-only violations, over-build, helper correctness.

### Findings + reconciliation (against physics)

| ID | Finding (sev) | Verdict | Reconciliation |
|----|----|----|----|
| W-1 | `_is_loopback("")` returned True, but an empty bind host = all interfaces → a set-but-empty `CHARON_SERVICE_HOST` passed the guard as "loopback" and served ungated on every interface (HIGH). | **ACCEPT — fix** | `_is_loopback` now treats only proven loopback (`127/8`, `::1`, `localhost`) as safe; `""`/`0.0.0.0`/`::`/unresolved hostnames are exposed → token required. Regression: `test_service_main.py`. |
| W-2 | FastAPI's auto docs (`/docs`,`/redoc`,`/openapi.json`) were ungated (bypass the per-route gate) and pull Swagger/ReDoc from a CDN — egress + API disclosure (MED). | **ACCEPT — fix** | `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`. The dashboard is the only UI. Regression: `test_auto_docs_are_disabled`. |
| W-3 | `/v1/config` returned `models.json` wholesale — a fat-fingered inline key would leak; trust-based, not structural (MED). | **ACCEPT — fix** | `show_config` projects each model onto the 8-field schema allowlist (`pools.py`), so no stray value can reach the surface even on misconfiguration — the no-creds-in-config invariant is now *structural*. Regression: `test_show_config_allowlists_model_fields_drops_stray_secret`. |
| W-4 | Dashboard built `onclick="showRun('${esc(id)}')"`; `esc()` doesn't escape `'`, so safety relied on `validate_task_id` forbidding quotes — fragile DOM-XSS if validation ever loosens (LOW–MED). | **ACCEPT — fix** | Removed the inline-onclick string sink entirely: `data-id` attributes (double-quoted, `esc`-escaped) + a delegated click listener. No JS-string-injection sink remains. |
| W-5 | `show_config._read` caught `JSONDecodeError`/`OSError` but not `UnicodeDecodeError` → a non-UTF-8 config 500'd instead of the intended per-file error dict (LOW). | **ACCEPT — fix** | Broadened to `(OSError, ValueError)` (both decode errors subclass `ValueError`). |
| W-6 | `require_token` fails OPEN when the token env is unset; a *direct* `uvicorn app --host 0.0.0.0` launch (not the `python -m` entrypoint) bypasses the bind guard (MED). | **ACCEPT — documented, not a request-layer check** | The bind guard lives in `__main__` because only there is the bind address known; the supported entrypoint enforces "exposed ⇒ token". A request-layer `client.host` loopback check was **rejected**: behind a reverse proxy every request *looks* loopback, so it would grant FALSE security to proxied external traffic — worse than honest documentation. The app docstring + `require_token` now state plainly: set `CHARON_SERVICE_TOKEN` for any non-loopback deployment. |
| W-7 | `?token=` query fallback leaks the token to logs/history (LOW–MED). | **ACCEPT as disclosed tradeoff** | It's what makes a plain browser URL work for the single operator; `compare_digest` is constant-time and zero external assets prevents a `Referer` leak. Disclosed in the docstring; harden via the reverse proxy. Bearer header is the non-browser path. |
| W-8 | Boundary AST scan is single-file/static while `api` (which imports the loop) is in-process; an indirect ref (`getattr`) would evade it (LOW–MED). | **ACKNOWLEDGE — pre-existing** | Not introduced here and not a live exploit; the container is the real boundary (the documented Tier-2b gap). Current code is clean (only `list_ledgers`/`show_ledger`/`show_config` referenced). |
| W-9 | `status` derives "complete" for a zero-acceptance-check ledger (LOW). | **ACKNOWLEDGE — unreachable** | `run_task` requires ≥1 `--accept`, so a real ledger always has a check and reads "incomplete" until verified. Left as-is. |
| — | XSS escaping on all live data paths (goal/provider/commit/config/ids), read-only-ness, and thinness: **clean** (reviewer confirmed). | — | No change. |

### Built + live proof

Read-only dashboard (project/run list → run view with progress/cost/handoffs/
checkpoints + a config pane), token-gated, self-contained HTML (**no external
assets → zero egress**). **Live-verified on `build-host`** against the real
cross-vendor failover ledgers: `/healthz` open; `/v1/runs` 401 without token /
real data (`complete`, 13 741 tokens, `acp`) with token or `?token=`; `/v1/config`
returns field-allowlisted models/pools (no secrets); `/` is 7 059 bytes with **0
external URL refs**; `/openapi.json` 404. Gate: **114 passing** (+ service tests
gated behind `[service]` via `importorskip` so the core gate stays stdlib-only),
ruff/mypy/boundary clean; the existing `test_boundary` still proves `app.py`
references no privileged-exec symbol.

WALK-BACK: none — additive; `service/app.py` stays read-only + 501-on-runs.
