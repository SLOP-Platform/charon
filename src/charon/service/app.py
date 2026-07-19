"""Mode B HTTP service + read-only web Ledger dashboard (ADR-0002 §2.4 surface #3;
ADR-0004 D7/R3).

DESIGN OF RECORD (DTC, 2026-06-24 / Tier 2b 2026-06-26 — see docs/REVIEW-LOG.md
and PLAN-tier2.md §8): the web process the host project reaches MUST NOT run the
privileged coordinator loop in-process. ADR-0002 §2.3 / INV-B4 require the
agent-spawning loop to live in its OWN process/container; the only real
blast-radius boundary for a live skip-permissions agent is that container, never
an in-process Python guard.

POST /v1/runs validates + writes one JSON job file to the filesystem queue
(CHARON_QUEUE_DIR/pending/<job_id>.json) and returns 202 Accepted. The separate
worker process (service/worker.py) picks up the job and runs api.run_task. This
file imports NO privileged-exec symbol — enforced structurally by
``tests/test_boundary.py`` (AST check for ``run_task``, ``coordinator``,
``dispatch``).

Posture (ADR-0004 D7): single-operator-on-your-fenced-box, **not** hardened
multi-tenant SaaS. Token-gated (``CHARON_SERVICE_TOKEN``); the container is the
security boundary; deploy behind a reverse proxy + HTTPS. Run it with
``python -m charon.service`` (which refuses a non-loopback bind without a token).
"""
from __future__ import annotations

import hmac
import json
import os
import uuid
from pathlib import Path

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Query
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "the HTTP service needs the [service] extra: pip install 'charon[service]'"
    ) from exc

from .. import __version__, api

_TOKEN_ENV = "CHARON_SERVICE_TOKEN"
_QUEUE_DIR_ENV = "CHARON_QUEUE_DIR"


def require_token(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> None:
    """Gate a request on the single-operator token (``CHARON_SERVICE_TOKEN``).

    Accepts ``Authorization: Bearer <t>`` (API clients) **or** ``?token=<t>`` (so
    the dashboard works from a plain browser URL). If the env var is unset the
    gate is open — intended only for a loopback dev bind; ``python -m
    charon.service`` refuses a non-loopback bind without a token, so a
    VPS-exposed instance is always gated. Constant-time compare."""
    # Fails OPEN when the token env is unset — intended ONLY for a loopback dev
    # bind. The "exposed ⇒ token required" rule is enforced at bind time by
    # ``python -m charon.service`` (the supported entrypoint), because only there
    # is the bind address known. Launching the ASGI app directly on a non-loopback
    # host without a token bypasses that guard — so always set CHARON_SERVICE_TOKEN
    # for any non-loopback deployment (and front it with a reverse proxy + HTTPS).
    expected = os.environ.get(_TOKEN_ENV, "")
    if not expected:
        return
    supplied = ""
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization[len("Bearer "):]
    elif token:
        supplied = token
    if not (supplied and hmac.compare_digest(supplied, expected)):
        raise HTTPException(status_code=401, detail="missing or invalid service token")


# docs_url/redoc_url/openapi_url=None: FastAPI's auto docs are (a) ungated (they
# bypass the per-route token gate) and (b) load Swagger/ReDoc from a CDN, which
# would violate the zero-egress posture. The dashboard is the only UI surface.
app = FastAPI(title="charon", version=__version__,
              docs_url=None, redoc_url=None, openapi_url=None)


class RunRequest(BaseModel):
    # `repo` is absent by design: the worker always runs in an auto-created
    # sandbox so a caller cannot direct a run at an arbitrary host path.
    goal: str
    accept: list[str]
    autonomy: str = "L0"
    budget: int = 8


def _enqueue(req: RunRequest) -> str:
    """Write a job record to the filesystem queue; return the job_id.

    The web process writes only. The worker (service/worker.py) reads and
    processes. This function never calls run_task, coordinator, or dispatch —
    the boundary is structural (test_boundary.py AST check)."""
    queue_str = os.environ.get(_QUEUE_DIR_ENV, "")
    if not queue_str:
        raise HTTPException(
            status_code=503,
            detail=(
                f"queue not configured: {_QUEUE_DIR_ENV} is not set. "
                "Deploy the charon worker container and set CHARON_QUEUE_DIR "
                "to the shared queue directory on both the web and worker processes."
            ),
        )
    job_id = uuid.uuid4().hex
    pending = Path(queue_str) / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    job: dict = {
        "job_id": job_id,
        "goal": req.goal,
        "accept": req.accept,
        "autonomy": req.autonomy,
        "budget": req.budget,
    }
    (pending / f"{job_id}.json").write_text(json.dumps(job))
    return job_id


@app.get("/healthz")
def healthz() -> dict:
    # Liveness only — intentionally unauthenticated (probes/load balancers).
    return {"status": "ok", "version": __version__}


@app.post("/v1/runs", status_code=202, dependencies=[Depends(require_token)])
def create_run(req: RunRequest) -> dict:
    # Enqueue the job; the worker container runs the privileged loop.
    job_id = _enqueue(req)
    return {"job_id": job_id, "status": "queued"}


@app.get("/v1/runs", dependencies=[Depends(require_token)])
def list_runs() -> dict:
    # Read-only: derived summaries of every ledger in the state dir.
    return {"runs": api.list_ledgers()}


@app.get("/v1/runs/{task_id}", dependencies=[Depends(require_token)])
def get_run(task_id: str) -> dict:
    # Read-only: derived ledger state. `task_id` is traversal-validated inside
    # the ledger boundary (ledger.validate_task_id); a bad id surfaces as a 404.
    try:
        return api.show_ledger(task_id)
    except Exception as exc:  # LedgerCorruption / invalid id / missing
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/config", dependencies=[Depends(require_token)])
def get_config() -> dict:
    # Read-only routing policy (models registry + role→pool order). Key-env refs
    # only; no provider secrets live in config.
    return api.show_config()


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_token)])
def dashboard() -> str:
    return _DASHBOARD_HTML


# --- minimal, self-contained dashboard (no external assets → zero egress) -----
# Read-only single pane: project/run list → click a run for progress/cost/handoff
# /checkpoints, plus the routing config. Watch-the-agent (live diffs/stream) stays
# CLI/TUI by decision (ADR-0004 D7); this view polls, it does not stream.
_DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>charon · ledger</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 14px/1.5 system-ui, sans-serif; margin: 0; }
  header { padding: .6rem 1rem; border-bottom: 1px solid #8884; display:flex;
           align-items:baseline; gap:1rem; }
  header h1 { font-size: 1rem; margin: 0; font-weight: 700; }
  header .muted { color:#8a8a8a; font-size:.8rem; }
  main { display: grid; grid-template-columns: minmax(260px, 22rem) 1fr; }
  #list, #detail { padding: .5rem 1rem; }
  #list { border-right: 1px solid #8884; }
  .run { padding:.4rem .5rem; border-radius:6px; cursor:pointer; }
  .run:hover { background:#8881; }
  .run.sel { background:#3b82f633; }
  .run .goal { font-weight:600; }
  .run .meta { color:#8a8a8a; font-size:.78rem; }
  .badge { display:inline-block; padding:0 .4rem; border-radius:10px; font-size:.72rem;
           font-weight:700; }
  .complete { background:#16a34a33; color:#15803d; }
  .incomplete { background:#f59e0b33; color:#b45309; }
  table { border-collapse: collapse; width: 100%; font-size: .85rem; }
  td, th { text-align:left; padding:.25rem .5rem; border-bottom:1px solid #8883;
           vertical-align: top; }
  code { font-family: ui-monospace, monospace; }
  h2 { font-size:.95rem; margin: 1rem 0 .4rem; }
  .pill { background:#8882; border-radius:6px; padding:0 .35rem; }
  .err { color:#dc2626; }
  button { font: inherit; }
</style></head>
<body>
<header><h1>charon · ledger</h1>
  <span class="muted" id="sub">read-only · single-operator</span>
  <span class="muted" style="margin-left:auto"><button onclick="load()">↻ refresh</button></span>
</header>
<main>
  <section id="list"><div class="muted">loading…</div></section>
  <section id="detail"><div class="muted">select a run</div></section>
</main>
<script>
const TOKEN = new URLSearchParams(location.search).get('token') || '';
const H = TOKEN ? { 'Authorization': 'Bearer ' + TOKEN } : {};
const $ = (s) => document.querySelector(s);
let SEL = null;

async function getJSON(url) {
  const r = await fetch(url, { headers: H });
  if (!r.ok) throw new Error(r.status + ' ' + r.statusText);
  return r.json();
}
function esc(s){ return String(s ?? '').replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function usd(u){ return u && u.cost_usd ? ('$' + Number(u.cost_usd).toFixed(4)) : '$0'; }
function tok(u){ return u ? (u.tokens ?? ((u.tokens_in||0)+(u.tokens_out||0))) : 0; }

async function load() {
  try {
    const { runs } = await getJSON('/v1/runs');
    const cfg = await getJSON('/v1/config').catch(() => null);
    renderList(runs, cfg);
    if (SEL && runs.some(r => r.task_id === SEL)) showRun(SEL);
    else if (runs.length) showRun(runs[runs.length-1].task_id);
  } catch (e) {
    $('#list').innerHTML = '<div class="err">'+esc(e.message)+
      ' — token? append <code>?token=…</code></div>';
  }
}
function renderList(runs, cfg) {
  // data-id + delegated clicks (no inline onclick): values go only into
  // double-quoted attributes via esc(), so no JS-string-injection sink exists.
  const items = runs.slice().reverse().map(r => `
    <div class="run ${r.task_id===SEL?'sel':''}" data-id="${esc(r.task_id)}">
      <div class="goal">${esc(r.goal)}</div>
      <div class="meta"><span class="badge ${esc(r.status)}">${esc(r.status)}</span>
        · ${r.checkpoints} ckpt · ${tok(r.usage)} tok · ${usd(r.usage)}
        ${r.providers && r.providers.length ? '· '+esc(r.providers.join(' → ')) : ''}</div>
    </div>`).join('');
  const ncfg = cfg && cfg.models ? Object.keys(cfg.models).length : 0;
  const npool = cfg && cfg.pools ? Object.keys(cfg.pools).length : 0;
  $('#list').innerHTML =
    `<div class="muted" style="margin-bottom:.4rem">${runs.length} run(s)`+
    ` · <a href="#" data-act="config">config</a>`+
    ` (${ncfg} models, ${npool} roles)</div>` +
    (items || '<div class="muted">no runs yet</div>');
}
$('#list').addEventListener('click', (ev) => {
  const cfg = ev.target.closest('[data-act="config"]');
  if (cfg) { ev.preventDefault(); showConfig(); return; }
  const run = ev.target.closest('.run');
  if (run) showRun(run.dataset.id);
});
async function showRun(id) {
  SEL = id;
  document.querySelectorAll('.run').forEach(e => e.classList.toggle('sel', e.dataset.id===id));
  try {
    const d = await getJSON('/v1/runs/' + encodeURIComponent(id));
    const cps = (d.checkpoints||[]).map((c) => `<tr>
      <td>${c.seq}</td><td><span class="pill">${esc(c.provider||'')}</span></td>
      <td><code>${esc((c.commit||'').slice(0,8))||'—'}</code></td>
      <td>${(c.verified||[]).length}/${(c.verified||[]).length+(c.remaining||[]).length}</td>
      <td>${c.usage?tok(c.usage):''}${c.usage&&c.usage.cost_usd?(' · '+usd(c.usage)):''}</td>
      <td class="muted">${esc(c.note||'')}</td>
      </tr>`).join('');
    const st = (d.remaining && d.remaining.length) ? 'incomplete' : 'complete';
    $('#detail').innerHTML = `
      <h2>${esc(d.goal)}</h2>
      <div class="muted"><code>${esc(d.task_id)}</code></div>
      <table style="margin-top:.6rem">
        <tr><td>status</td><td><span class="badge ${st}">${st}</span></td></tr>
        <tr><td>verified</td><td>${esc((d.verified||[]).join(', ')||'—')}</td></tr>
        <tr><td>remaining</td><td>${esc((d.remaining||[]).join(', ')||'—')}</td></tr>
        <tr><td>cost</td><td>${usd(d.usage)} · ${tok(d.usage)} tokens</td></tr>
        <tr><td>handoffs</td><td>${esc((d.provider_history||[]).join(' → ')||'—')}</td></tr>
        <tr><td>lkg</td><td><code>${esc((d.lkg_ref||'').slice(0,12))}</code></td></tr>
      </table>
      <h2>checkpoints</h2>
      <table><tr><th>#</th><th>provider</th><th>commit</th><th>accept</th><th>usage</th><th>note</th></tr>
        ${cps || '<tr><td colspan="6" class="muted">none</td></tr>'}</table>`;
  } catch (e) { $('#detail').innerHTML = '<div class="err">'+esc(e.message)+'</div>'; }
}
async function showConfig() {
  SEL = null;
  try {
    const c = await getJSON('/v1/config');
    const models = c.models || {};
    const rows = Object.entries(models).map(([k,v]) => `<tr>
      <td><code>${esc(k)}</code></td><td>${esc(v.cost_tier)}</td>
      <td>${v.code_safe?'✓':'·'}</td><td>${esc(v.key_env||'')}</td></tr>`).join('');
    const pools = Object.entries(c.pools||{}).map(([role,ms]) =>
      `<tr><td><b>${esc(role)}</b></td><td>${esc((ms||[]).join('  →  '))}</td></tr>`).join('');
    $('#detail').innerHTML = `
      <h2>roles → pools</h2>
      <table><tr><th>role</th><th>pool (priority order)</th></tr>
        ${pools||'<tr><td colspan="2" class="muted">none</td></tr>'}</table>
      <h2>models</h2>
      <table><tr><th>id</th><th>tier</th><th>code-safe</th><th>key env</th></tr>
        ${rows||'<tr><td colspan="4" class="muted">none</td></tr>'}</table>`;
  } catch (e) { $('#detail').innerHTML = '<div class="err">'+esc(e.message)+'</div>'; }
}
load();
</script>
</body></html>"""
