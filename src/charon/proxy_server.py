"""HTTP serving shell for the observing proxy (ADR-0004 R1).

Wraps ``GatewayProxy.observe`` in a tiny OpenAI-compatible reverse proxy that the
ACP agent points at (its provider ``baseURL`` → this server). For each call the
server forwards to the configured upstream — injecting the real provider key, so
credentials stay in Charon's control plane and never reach the agent — observes
the response (status / usage / returned model), and relays it back unchanged.

Stdlib only (``http.server`` + ``urllib``). This is the serving plumbing on top of
the unit-tested observation core; it is exercised both by an in-process
integration test (mock upstream) and live via a real OpenCode-Go call.
"""
from __future__ import annotations

import collections
import hashlib
import hmac
import http.cookies
import http.server
import json
import socketserver
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .cache import SemanticCache
from .consensus import ConsensusRouter
from .guardrails import Guardrails
from .netutil import is_loopback
from .observability import Observability
from .policy_router import PolicyRouter
from .proxy import GatewayProxy
from .quality_scorer import QualityScorer
from .request_inspector import RequestInspector
from .response_normalizer import NormalizeMode, ResponseNormalizer
from .session_affinity import SessionAffinity
from .speculative_execution import SpeculativeExecutor
from .spend_limits import SpendLimiter
from .virtual_keys import VirtualKeyManager


@dataclass(frozen=True)
class UpstreamRoute:
    """Where one agent-facing model id is forwarded (multi-provider pools)."""

    upstream_base: str
    api_key: str | None = None
    upstream_model: str | None = None  # rewrite the body's model to this id upstream
    pool_id: str | None = None  # observe under this id (the router's pool id) if set
    provider: str | None = None  # display label for failover visibility (X-Charon-Provider)
    strip_v1: bool | None = None  # per-provider quirk; None → use the server default

    @property
    def label(self) -> str:
        """Human-facing provider id for failover headers/logs — never a secret. Uses
        host[:port] (NOT netloc) so any ``user:pass@`` userinfo in a misconfigured
        base never surfaces in a header/console (P4 review)."""
        if self.provider:
            return self.provider
        parts = urlsplit(self.upstream_base)
        host = parts.hostname or self.upstream_base
        return f"{host}:{parts.port}" if parts.port else host

_SKIP_HEADERS = {"host", "authorization", "content-length", "connection",
                 "accept-encoding", "proxy-authorization"}
_DEFAULT_UA = "charon-proxy/0.1"
# Library-default UAs upstream bot-protection bans (Cloudflare 1010); normalize
# these to the proxy's own identity so an internal urllib caller isn't blocked.
_BANNED_UA_PREFIXES = ("python-urllib", "python-requests")
# Cap the streamed bytes buffered while looking for the response `model` id (the
# silent-downgrade check before committing a stream); bounds memory on a stream
# that never carries a model field.
_STREAM_HEAD_CAP = 65536

# Self-contained gateway console (P4) — NO external assets (zero egress, like the
# read-only dashboard). Polls /charon/status; carries the bearer via ?token= so a
# browser URL works behind the token gate.
_CONSOLE_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Charon Gateway</title><style>
body{font:14px system-ui,sans-serif;margin:1.5rem;background:#0b0e14;color:#cdd6f4}
h1{font-size:1.2rem} h2{font-size:1rem;margin-top:1.4rem;color:#89b4fa}
table{border-collapse:collapse;width:100%;margin-top:.3rem}
th,td{text-align:left;padding:.3rem .6rem;border-bottom:1px solid #313244}
.cool{color:#f38ba8}.ok{color:#a6e3a1}.muted{color:#6c7086}
.tier{background:#89b4fa;color:#11111b;border-radius:3px;padding:0 .3rem;font-size:.8rem}
code{background:#1e1e2e;padding:.1rem .3rem;border-radius:3px}
</style></head><body>
<h1>Charon Gateway <span class=muted id=ts></span></h1>
<div style="margin-bottom:.6rem">
<a href="/charon/setup" id=setupLink style="color:#89b4fa;text-decoration:none">⚙ Setup</a>
</div>
<div id=usage></div>
<h2>Providers</h2><table id=providers><thead><tr><th>provider<th>served<th>failed
<th>errors<th>cost $<th>last<th>cooldown</tr></thead><tbody></tbody></table>
<h2>Pools</h2><table id=pools><thead><tr><th>pool<th>tier<th>chain</tr></thead>
<tbody></tbody></table>
<h2>Recent failovers</h2><div id=failovers class=muted>none yet</div>
<script>
const tok=new URLSearchParams(location.search).get('token');
const q=tok?('?token='+encodeURIComponent(tok)):'';
const setupLink = document.getElementById('setupLink');
if (tok) setupLink.href = '/charon/setup?token=' + encodeURIComponent(tok);
function esc(s){return String(s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function tick(){
 let r; try{r=await fetch('/charon/status'+q)}catch(e){return}
 if(!r.ok)return; const d=await r.json();
 document.getElementById('ts').textContent=new Date().toLocaleTimeString();
 document.getElementById('usage').innerHTML='<b>Usage:</b> '+d.usage.tokens_in+
   ' in / '+d.usage.tokens_out+' out / $'+d.usage.cost_usd;
 const pb=document.querySelector('#providers tbody');pb.innerHTML='';
 for(const [n,s] of Object.entries(d.providers)){const cd=d.cooldown_seconds[n];
  pb.insertAdjacentHTML('beforeend','<tr><td><code>'+esc(n)+'</code><td>'+s.served+
   '<td>'+s.failed+'<td>'+(s.errors||0)+'<td>'+(s.cost||0).toFixed(4)+'<td>'+esc(s.last_status)+
   '<td>'+(cd?('<span class=cool>'+cd+'s</span>'):'<span class=ok>ok</span>')+'</tr>')}
 const lb=document.querySelector('#pools tbody');lb.innerHTML='';
 const TIERS=['low','med','high'];
 for(const [m,ps] of Object.entries(d.pools)){
  const tag=TIERS.includes(m)?'<span class=tier>tier</span>':'';
  lb.insertAdjacentHTML('beforeend',
   '<tr><td><code>'+esc(m)+'</code><td>'+tag+'<td>'+ps.map(esc).join(' &rarr; ')+'</tr>')}
 const fb=document.getElementById('failovers');const ev=d.recent_failovers.slice(-15).reverse();
 fb.innerHTML=ev.length?ev.map(e=>esc(e.model)+': '+e.failovers.map(f=>esc(f.provider)+
   '='+esc(f.status)).join(', ')+' &rarr; '+esc(e.served_by)).join('<br>'):'none yet';
}
tick();setInterval(tick,2000);
</script></body></html>"""

# Self-contained work/board panel (P5, WORK-OBSERVABILITY follow-on). Reads
# /charon/work?json=0 for the HTML table and /charon/work?json=1 for raw JSON.
# Purely read-only; no mutation; no secrets rendered.
_WORK_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Charon Work</title><style>
body{font:14px system-ui,sans-serif;margin:1.5rem;background:#0b0e14;color:#cdd6f4}
h1{font-size:1.2rem}h2{font-size:1rem;margin-top:1.4rem;color:#89b4fa}
table{border-collapse:collapse;width:100%;margin-top:.3rem}
th,td{text-align:left;padding:.3rem .6rem;border-bottom:1px solid #313244}
.comp{color:#a6e3a1}.prog{color:#f9e2af}.blkd{color:#f38ba8}.esc{color:#fab387}
code{background:#1e1e2e;padding:.1rem .3rem;border-radius:3px}
.muted{color:#6c7086}
</style></head><body>
<h1>Charon Work <span class=muted id=ts></span></h1>
<div id=panel></div>
<script>
const tok=new URLSearchParams(location.search).get('token');
const q=tok?('?token='+encodeURIComponent(tok)):'';
function esc(s){return String(s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function cls(s){return{'complete':'comp','in-progress':'prog',
 'blocked':'blkd','ready':'prog','escaped':'esc','budget':'esc'}[s]||''}
async function load(){
 let r; try{r=await fetch('/charon/work?json=1'+q)}catch(e){return}
 if(!r.ok)return; const d=await r.json();
 document.getElementById('ts').textContent=new Date().toLocaleTimeString();
 if(!d.runs||!d.runs.length){
  document.getElementById('panel').innerHTML=
   '<p class=muted>no runs found — run &#96;charon work --units …&#96; first</p>';return}
 const heads='<th>run id<th>status<th>task / goal'
 +'<th>checks<th>tokens in/out<th>cost $<th>lkg';
 let h='<table><tr>'+heads;
 for(const u of d.runs){
  const goal=u.goal?u.goal.substring(0,60):'';
  h+='<tr><td><code>'+esc(u.run_id)+'</code><td class='+cls(u.status)+'>'+esc(u.status)+
   '<td><span title="'+esc(u.goal||'')+'">'+esc(u.task_id)+'</span> '+
   (goal?'<span class=muted>'+esc(goal)+'</span>':'')+
   '<td>'+u.verified_count+' / '+u.remaining_count+
   '<td>'+esc(u.usage.tokens_in)+' / '+esc(u.usage.tokens_out)+
   '<td>'+esc(u.usage.cost_usd)+
   '<td><code>'+esc(u.lkg_ref||'—')+'</code>';
 }
 h+='</table>';
 document.getElementById('panel').innerHTML=h;
}
load();setInterval(load,5000);
</script></body></html>"""

# Self-contained web SETUP page (read-write). Posts to /charon/{providers,models,
# pools}; the key field is a password input and is never rendered back.
_SETUP_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Charon Setup</title><style>
body{font:14px system-ui,sans-serif;margin:1.5rem;max-width:46rem;background:#0b0e14;color:#cdd6f4}
h1{font-size:1.2rem}h2{font-size:1rem;color:#89b4fa;margin-top:1.4rem}
fieldset{border:1px solid #313244;border-radius:6px;margin:.6rem 0;padding:.6rem .8rem}
label{display:inline-block;min-width:7rem}
input{background:#1e1e2e;color:#cdd6f4;border:1px solid #313244;
  border-radius:4px;padding:.25rem .4rem;margin:.15rem 0}
button{background:#89b4fa;color:#11111b;border:0;border-radius:4px;
  padding:.3rem .8rem;cursor:pointer;margin-top:.3rem}
code{background:#1e1e2e;padding:.1rem .3rem;border-radius:3px}.ok{color:#a6e3a1}.bad{color:#f38ba8}
table{border-collapse:collapse;width:100%}
td,th{text-align:left;padding:.2rem .5rem;border-bottom:1px solid #313244}
</style></head><body>
<h1>Charon Setup</h1>
<div style="margin-bottom:.6rem">
<a href="/" id=dashLink style="color:#89b4fa;text-decoration:none">← Dashboard</a>
</div>
<div id=msg class=muted></div>
<fieldset><h2>Add provider</h2>
<div><label>name</label>
  <input id=pname list=presets placeholder="openrouter / deepseek / my-provider">
  <datalist id=presets></datalist></div>
<div><label>base URL</label><input id=pbase size=36 placeholder="(blank if it's a preset)"></div>
<div><label>key env</label><input id=pkenv placeholder="(blank = preset default)"></div>
<div><label>API key</label>
  <input id=pkey type=password size=36 placeholder="paste key (stored 0600)"></div>
<button onclick=addProvider()>Add provider</button></fieldset>
<fieldset><h2>Add model</h2>
<div><label>model id</label><input id=mid placeholder="id clients request"></div>
<div><label>provider</label><input id=mprov></div>
<div><label>upstream id</label><input id=mups placeholder="(blank = same)"></div>
<div><label>free?</label><input id=mfree type=checkbox></div>
<button onclick=addModel()>Add model</button>
<div style="margin-top:.5rem;border-top:1px solid #313244;padding-top:.4rem">
  <label>or import all</label>
  <input id=ifree type=checkbox><span class=muted>free only</span>
  <button onclick=importModels()>Import provider's catalog</button>
  <div class=muted>imports every model the provider above advertises
    (catalog only; pools stay curated)</div>
</div></fieldset>
<fieldset><h2>Failover pool</h2>
<div><label>pool id</label><input id=plid placeholder="auto"></div>
<div><label>models</label><input id=plmem size=36 placeholder="comma,separated,model,ids"></div>
<button onclick=addPool()>Create pool</button></fieldset>
<fieldset><h2>Tiers</h2>
<div class=muted>canonical tiers low&rarr;med&rarr;high; members are model ids from above</div>
<div><label>low</label><input id=tlow size=36 placeholder="comma,separated,model,ids"></div>
<div><label>med</label><input id=tmed size=36 placeholder="comma,separated,model,ids"></div>
<div><label>high</label><input id=thigh size=36 placeholder="comma,separated,model,ids"></div>
<div><label>aliases</label><input id=talias size=36 placeholder="opus=high, sonnet=med"></div>
<button onclick=setTiers()>Save tiers</button></fieldset>
<fieldset><h2>Global fallback</h2>
<div class=muted>try these when ANY model's primary fails (comma-separated, ordered)</div>
<div><label>providers</label><input id=fbprov size=36 placeholder="e.g. opencode-go"></div>
<button onclick=saveFallback()>Save fallback</button></fieldset>
<h2>Current config</h2><div id=cfg></div>
<script>
const tok=new URLSearchParams(location.search).get('token');
const dashLink = document.getElementById('dashLink');
if (tok) dashLink.href = '/?token=' + encodeURIComponent(tok);
const H=Object.assign({'Content-Type':'application/json'},tok?{'Authorization':'Bearer '+tok}:{});
function esc(s){return String(s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function val(id){return document.getElementById(id).value.trim()}
function msg(t,ok){const m=document.getElementById('msg');m.textContent=t;m.className=ok?'ok':'bad'}
async function post(path,body){
  const r=await fetch(path,{method:'POST',headers:H,body:JSON.stringify(body)});
  const d=await r.json().catch(()=>({})); return {ok:r.ok,d};}
async function addProvider(){
  const b={name:val('pname'),base_url:val('pbase')||null,
    key_env:val('pkenv')||null,key:val('pkey')||null};
  const {ok,d}=await post('/charon/providers',b);
  if(ok){document.getElementById('pkey').value='';
    msg(('added provider '+b.name)+'  '+(d.probe?('('+d.probe.message+
      (d.probe.models_count?', '+d.probe.models_count+' models':'')+')'):''),true);
    load();
  }else{msg('error: '+(d.error&&d.error.message),false);}}
async function addModel(){
  const free=document.getElementById('mfree').checked;
  const b={id:val('mid'),provider:val('mprov')||null,
    upstream_model:val('mups')||null,free:free,cost_rank:free?0:1000};
  const {ok,d}=await post('/charon/models',b);
  msg(ok?('added model '+b.id):('error: '+(d.error&&d.error.message)),ok); if(ok)load();}
async function importModels(){
  const prov=val('mprov');
  if(!prov){msg('enter a provider name above first',false);return}
  msg('importing models from '+prov+'…',true);
  const b={provider:prov,free_only:document.getElementById('ifree').checked};
  const {ok,d}=await post('/charon/models/import',b);
  msg(ok?('imported '+d.added+' model(s)'+(d.skipped?(' ('+d.skipped+' skipped)'):'')):
    ('error: '+(d.error&&d.error.message)),ok); if(ok)load();}
async function addPool(){
  const b={id:val('plid')||'auto',members:val('plmem').split(',').map(s=>s.trim()).filter(Boolean)};
  const {ok,d}=await post('/charon/pools',b);
  msg(ok?('created pool '+b.id):('error: '+(d.error&&d.error.message)),ok); if(ok)load();}
function mids(id){return val(id).split(',').map(s=>s.trim()).filter(Boolean)}
async function setTiers(){
  const aliases={};
  val('talias').split(',').map(s=>s.trim()).filter(Boolean).forEach(p=>{
    const i=p.indexOf('='); if(i>0)aliases[p.slice(0,i).trim()]=p.slice(i+1).trim();});
  const b={order:['low','med','high'],
    members:{low:mids('tlow'),med:mids('tmed'),high:mids('thigh')},aliases};
  const {ok,d}=await post('/charon/tiers',b);
  msg(ok?'saved tiers':('error: '+(d.error&&d.error.message)),ok); if(ok)load();}
async function saveFallback(){
  const provs=val('fbprov').split(',').map(s=>s.trim()).filter(Boolean);
  const {ok,d}=await post('/charon/fallback',{providers:provs});
  msg(ok?('saved fallback: '+provs.join(', ')):('error: '+(d.error&&d.error.message)),ok);
  if(ok)load();}
async function removeProvider(n){
  const {ok,d}=await post('/charon/remove',{kind:'provider',name:n});
  msg(ok?('removed provider '+n):('error: '+(d.error&&d.error.message)),ok);if(ok)load();}
async function removeModel(n){
  const {ok,d}=await post('/charon/remove',{kind:'model',name:n});
  msg(ok?('removed model '+n):('error: '+(d.error&&d.error.message)),ok);if(ok)load();}
async function toggleModel(id,en){
  const {ok,d}=await post('/charon/'+(en?'enable':'disable'),{id:id});
  msg(ok?(id+' '+(en?'enabled':'disabled')):('error: '+(d.error&&d.error.message)),ok);
  if(ok)load();}
async function load(){
  let r; try{r=await fetch('/charon/config',{headers:H})}catch(e){return}
  if(!r.ok){msg('not authorized — append ?token=… to the URL',false);return}
  const d=await r.json();
  document.getElementById('presets').innerHTML=
    (d.presets||[]).map(p=>'<option value="'+esc(p)+'">').join('');
  let h='<table><tr><th>provider<th>base<th>key<th></tr>';
  for(const[n,p]of Object.entries(d.providers||{}))h+='<tr><td><code>'+esc(n)+
    '</code><td>'+esc(p.base_url||'(preset)')+'<td>'+
    (p.key_set?'<span class=ok>set</span>':'<span class=bad>missing</span>')+
    '<td><button onclick=removeProvider("'+esc(n)
+    '") style="background:#f38ba8;font-size:.8rem">remove</button></tr>';
  h+='</table><b>models:</b><br><table><tr><th>id<th>enabled<th></tr>';
  for(const[n,m]of Object.entries(d.models||{})){
    const en=m.enabled!==false;
    const label=en?'disable':'enable';
    h+='<tr><td><code>'+esc(n)+'</code><td>'+
      (en?'<span class=ok>yes</span>':'<span class=bad>no</span>')+
      '<td><button onclick=toggleModel("'+esc(n)+'",'+(!en)+')'
      +' style="font-size:.8rem">'+label+'</button>'
      +'<button onclick=removeModel("'+esc(n)+'")'
      +' style="background:#f38ba8;font-size:.8rem;margin-left:.3rem">remove</button></tr>';
  }
  h+='</table><b>pools:</b> '+
     Object.entries(d.pools||{}).map(([k,v])=>esc(k)+'=['+v.map(esc).join(', ')+']').join('  ');
  if(d.fallback&&d.fallback.length)h+='<br><b>global fallback:</b> '+d.fallback.map(esc).join(', ');
  document.getElementById('cfg').innerHTML=h;}
load();
</script></body></html>"""


def _extract(raw: bytes, content_type: str) -> dict:
    """Pull a ``{model, usage}`` view out of an upstream response — JSON for a
    normal completion, or the SSE ``data:`` chunks for a streamed one (agents like
    OpenCode stream). Returns {} if nothing parseable."""
    text = raw.decode("utf-8", "replace")
    if "text/event-stream" in content_type or text.lstrip().startswith("data:"):
        model = ""
        usage = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload in ("", "[DONE]"):
                continue
            try:
                obj = json.loads(payload)
            except Exception:  # noqa: BLE001
                continue
            model = model or obj.get("model", "")
            if obj.get("usage"):
                usage = obj["usage"]  # final SSE chunk carries usage (include_usage)
        out: dict = {}
        if model:
            out["model"] = model
        if usage:
            out["usage"] = usage
        return out
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return {}


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # close-delimited; works for SSE without length

    def log_message(self, *args) -> None:  # keep the coordinator's stdout clean
        pass

    def do_POST(self) -> None:
        self._handle()

    def do_GET(self) -> None:
        self._handle()

    def _json(self, status: int, obj: dict) -> None:
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._maybe_set_token_cookie()
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _html(self, html: str) -> None:
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._maybe_set_token_cookie()
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _authorized(self, token: str) -> bool:
        """Bearer token via ``Authorization`` header, ``?token=`` query, or
        ``charon_token`` cookie; constant-time compare to avoid leaking via timing."""
        presented = ""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            presented = auth[len("Bearer "):].strip()
        if not presented:
            qs = parse_qs(urlsplit(self.path).query)
            presented = (qs.get("token") or [""])[0]
        if not presented:
            cookie_header = self.headers.get("Cookie", "")
            cookies = http.cookies.SimpleCookie()
            cookies.load(cookie_header)
            cookie_token = cookies.get("charon_token")
            if cookie_token:
                presented = cookie_token.value
        return bool(presented) and hmac.compare_digest(presented, token)

    def _maybe_set_token_cookie(self) -> None:
        """If this request authenticated via ``?token=``, set a short-lived cookie
        so subsequent page loads don't need the token in the URL."""
        v = getattr(self, '_set_token_cookie', None)
        if v:
            self.send_header("Set-Cookie",
                f"charon_token={v}; Path=/; HttpOnly; SameSite=Lax; Max-Age=900")

    # ---- helpers ---------------------------------------------------------

    def _write(self, data: bytes) -> bool:
        """Write to the client; False if the client hung up (so we stop)."""
        try:
            self.wfile.write(data)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    def _drain(self, resp) -> bytes:
        out: list[bytes] = []
        try:
            while True:
                c = resp.read(8192)
                if not c:
                    break
                out.append(c)
        except Exception:  # noqa: BLE001
            pass
        return b"".join(out)

    def _send_resp_headers(self, status: int, ctype: str, provider: str | None,
                           failovers: list[dict], downgrade: bool) -> None:
        """Send status + Content-Type + the failover-visibility headers (ADR D3)."""
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if provider:
            self.send_header("X-Charon-Provider", provider)
        self.send_header("X-Charon-Failovers", str(len(failovers)))
        if failovers:
            self.send_header("X-Charon-Failover-Reasons",
                             "; ".join(f"{f['provider']}={f['status']}" for f in failovers))
        if downgrade:
            self.send_header("X-Charon-Downgrade", "served a different model than requested")
        self._maybe_set_token_cookie()
        self.end_headers()

    def _build_upstream_req(self, srv, route: UpstreamRoute, orig_bj: dict,
                            raw_body: bytes) -> urllib.request.Request:
        """Build the upstream request for ONE attempt from the ORIGINAL request —
        each provider gets its own ``upstream_model`` (ADR R10b), and the client
        query string is dropped so our ``?token=`` bearer never leaks upstream
        (security review HIGH)."""
        bj = dict(orig_bj)
        if bj:
            if route.upstream_model:
                bj["model"] = route.upstream_model
            if bj.get("stream") is True:
                opts = dict(bj.get("stream_options") or {})
                opts["include_usage"] = True
                bj["stream_options"] = opts
            data: bytes | None = json.dumps(bj).encode()
        else:
            data = raw_body or None

        path = urlsplit(self.path).path  # PATH ONLY — never forward the query string
        strip_v1 = route.strip_v1 if route.strip_v1 is not None else srv.strip_v1
        if strip_v1 and path.startswith("/v1"):
            path = path[len("/v1"):]  # upstream_base already ends in /v1
        url = route.upstream_base.rstrip("/") + path

        req = urllib.request.Request(url, data=data, method=self.command)
        for hk in self.headers.keys():
            # User-Agent is normalized separately (below) — never forwarded raw.
            if hk.lower() not in _SKIP_HEADERS and hk.lower() != "user-agent":
                req.add_header(hk, self.headers[hk])
        req.add_header("Content-Type", "application/json")
        # Egress identity: forward the agent's real UA (some gateways 403 an unknown
        # one), but replace an absent/library-default UA — "Python-urllib/3.x" trips
        # Cloudflare 1010 (→403). Live-verified.
        client_ua = self.headers.get("User-Agent", "")
        if client_ua and not client_ua.lower().startswith(_BANNED_UA_PREFIXES):
            req.add_header("User-Agent", client_ua)
        else:
            req.add_header("User-Agent", _DEFAULT_UA)
        if route.api_key:
            req.add_header("Authorization", f"Bearer {route.api_key}")
        return req

    def _handle(self) -> None:
        srv: GatewayProxyServer = self.server  # type: ignore[assignment]

        # Anti-DNS-rebinding (security review HIGH): on a loopback bind, reject a Host
        # header that isn't a loopback literal — defeats the rebinding that would
        # otherwise let a web page drive the ungated-default gateway and exfiltrate keys.
        if srv.require_loopback_host:
            hosthdr = self.headers.get("Host", "")
            if hosthdr and not is_loopback(urlsplit("//" + hosthdr).hostname or ""):
                self._json(403, {"error": {"message": "host not allowed"}})
                return

        # Token gate (gateway mode). Default ``token=None`` keeps the bare proxy
        # open — exactly its prior behavior; a set token requires it on every call.
        if srv.token is not None and not self._authorized(srv.token):
            self._json(401, {"error": {"message": "missing or invalid bearer token"}})
            return

        # If auth was via ?token= query param, set a short-lived cookie so
        # subsequent page loads don't need the token in the URL.
        if srv.token is not None:
            qs = parse_qs(urlsplit(self.path).query)
            qt = qs.get("token")
            if qt and qt[0]:
                self._set_token_cookie = srv.token

        # Aggregated model list (gateway mode). Served locally — never forwarded —
        # and field-allowlisted to ids only (no key_env/upstream_base leak, ADR R4).
        # Pool virtual IDs (e.g. auto, tier names) are EXCLUDED — they are internal
        # routing concepts, not real models (MODEL-DISCOVERY).
        path_only = urlsplit(self.path).path.rstrip("/")
        if (self.command == "GET" and srv.model_ids is not None
                and path_only in ("/v1/models", "/models")):
            # Exclude pool virtual IDs that are NOT also concrete models
            # (a model named "auto" or "low" is a real model, not a pool).
            pool_only = set(srv.pools.keys()) - set(srv.routes.keys())
            exposed = [m for m in srv.model_ids if m not in pool_only]
            entries: list[dict] = []
            for m in exposed:
                entry: dict = {"id": m, "object": "model", "owned_by": "charon"}
                meta = srv.model_meta.get(m, {})
                for k in ("context_window", "max_tokens", "reasoning", "vision", "audio"):
                    if k in meta:
                        entry[k] = meta[k]
                entries.append(entry)
            self._json(200, {"object": "list", "data": entries})
            return

        # Gateway console + status (P4) — gateway mode only, token-gated above.
        if self.command == "GET" and srv.model_ids is not None:
            if path_only == "/charon/status":
                self._json(200, srv.status_snapshot())
                return
            if path_only in ("", "/charon"):
                self._html(_CONSOLE_HTML)
                return

        # Web setup (read-WRITE) — only when a setup handler is wired (gateway mode,
        # token-gated above). A CSRF/Origin guard backs the token gate on writes.
        if srv.setup_handler is not None and srv.model_ids is not None:
            if self.command == "GET" and path_only == "/charon/setup":
                self._html(_SETUP_HTML)
                return
            if self.command == "GET" and path_only == "/charon/config":
                status, obj = srv.setup_handler("summary", {})
                self._json(status, obj)
                return
            if self.command == "POST" and path_only in (
                    "/charon/providers", "/charon/models", "/charon/models/import",
                    "/charon/pools", "/charon/tiers", "/charon/fallback",
                    "/charon/enable", "/charon/disable", "/charon/remove"):
                host = self.headers.get("Host", "")
                origin = self.headers.get("Origin")
                if origin and urlsplit(origin).netloc != host:  # CSRF: cross-origin write
                    self._json(403, {"error": {"message": "cross-origin write refused"}})
                    return
                sfs = self.headers.get("Sec-Fetch-Site")
                if sfs and sfs not in ("same-origin", "none"):
                    self._json(403, {"error": {"message": "cross-site write refused"}})
                    return
                length = int(self.headers.get("Content-Length") or 0)
                if length > srv.max_body_bytes:
                    self._json(413, {"error": {"message": "request body too large"}})
                    return
                raw = self.rfile.read(length) if length else b""
                try:
                    payload = json.loads(raw) if raw else {}
                except Exception:  # noqa: BLE001
                    self._json(400, {"error": {"message": "invalid JSON"}})
                    return
                if not isinstance(payload, dict):
                    self._json(400, {"error": {"message": "expected a JSON object"}})
                    return
                try:
                    status, obj = srv.setup_handler(path_only[len("/charon/"):], payload)
                except ValueError as exc:
                    self._json(400, {"error": {"message": str(exc)}})  # validation msg only
                    return
                except Exception:
                    self._json(400, {"error": {"message": "setup write failed"}})  # no path leak
                    return
                self._json(status, obj)
                return

        # Work/board panel (P5, WORK-OBSERVABILITY follow-on) — read-only,
        # token-gated above. /charon/work returns HTML; add ?json=1 for raw JSON.
        if self.command == "GET" and path_only == "/charon/work":
            from . import console_work
            try:
                runs = console_work.gather_runs()
            except Exception:  # noqa: BLE001
                runs = []
            qs = parse_qs(urlsplit(self.path).query)
            if qs.get("json") == ["1"]:
                self._json(200, {"runs": runs})
            else:
                self._html(_WORK_HTML)
            return

        # Read the client request (size-capped — memory-DoS guard on an exposed bind).
        length = int(self.headers.get("Content-Length") or 0)
        if length > srv.max_body_bytes:
            self._json(413, {"error": {"message": "request body too large"}})
            return
        raw_body = self.rfile.read(length) if length else b""

        orig_bj: dict = {}
        requested = ""
        try:
            orig_bj = json.loads(raw_body) if raw_body else {}
            requested = orig_bj.get("model", "")
        except Exception:  # noqa: BLE001
            pass

        chain = srv.chain_for(requested)
        if not chain:
            srv.observer.observe(requested, 502, {}, {}, count_usage=False)
            self._json(502, {"error": {"message": (
                f"no route for model {requested!r} — no providers configured; "
                "run 'charon setup' or open http://127.0.0.1:8080/charon/setup"
            )}})
            return

        # ── spend cap check (before any upstream call) ──────────────────
        if srv.spend_limiter is not None:
            est_tokens = max(len(raw_body) // 4, 100)
            est_cost = est_tokens * 0.0000015  # nominal per-token floor
            dec = srv.spend_limiter.check(est_cost)
            if not dec.allowed:
                self._json(402, {"error": {"message": dec.reason,
                               "remaining": dec.remaining}})
                return

        # ── guardrail request scan ──────────────────────────────────────
        if srv.guardrails is not None:
            msgs = orig_bj.get("messages", [])
            violations, _ = srv.guardrails.scan_request(msgs)
            blocking = [v for v in violations if v.severity == "BLOCK"]
            if blocking:
                self._json(400, {"error": {
                    "message": "request blocked by guardrails",
                    "violations": [{"pattern": v.pattern, "message": v.message}
                                   for v in blocking]
                }})
                return

        # ── cache check ─────────────────────────────────────────────────
        if srv.semantic_cache is not None:
            cache_key = hashlib.sha256(raw_body).hexdigest()
            cached = srv.semantic_cache.get(cache_key)
            if cached is not None:
                ctype = cached.headers.get("Content-Type", "application/json")
                self._send_resp_headers(200, ctype, "cache", [], False)
                self.wfile.write(b"X-Cache-Status: HIT\r\n\r\n")
                self._write(cached.content)
                srv.note_request(requested, "cache-hit", 200, 0.0, [])
                return

        is_stream = orig_bj.get("stream") is True
        ordered = srv.order_by_cooldown(chain)  # fresh providers first, cooled last (R7)

        # ── quality-aware routing ──────────────────────────────────────
        if srv.quality_scorer is not None and ordered:
            scored = [(srv.quality_scorer.score(r.label), r) for r in ordered]
            filtered = [r for s, r in scored if s >= 0.5]
            if filtered:
                ordered = filtered
            # else: all below floor → use original order (no starvation)

        failovers: list[dict] = []

        for i, route in enumerate(ordered):
            more = i < len(ordered) - 1
            okey = route.pool_id or requested  # exclusion/observe key (orchestrator compat)
            expected = route.upstream_model or requested or None
            req = self._build_upstream_req(srv, route, orig_bj, raw_body)

            try:
                resp = urllib.request.urlopen(req, timeout=srv.fwd_timeout)
                status, rhdrs = resp.status, dict(resp.headers)
            except urllib.error.HTTPError as exc:
                resp, status, rhdrs = exc, exc.code, dict(exc.headers)
            except Exception:  # provider unreachable → fail over (don't 502 outright)
                srv.observer.record(srv.observer.classify(okey, 503, {}, {},
                                    expected_model=expected), count_usage=False)
                srv.set_cooldown(route, None)
                if more:  # count only providers we actually move PAST
                    failovers.append({"provider": route.label, "status": "unreachable",
                                      "reason": "connection error"})
                    continue
                self._send_resp_headers(502, "application/json", route.label, failovers, False)
                self._write(json.dumps(
                    {"error": {"message": "all upstreams unreachable"}}).encode())
                srv.note_request(requested, route.label, "unreachable", 0.0, failovers)
                return

            ctype = rhdrs.get("Content-Type", "application/json")
            try:
                # ---- non-200 ----
                if status != 200:
                    body_bytes = self._drain(resp)
                    obs_body = _extract(body_bytes, ctype)
                    obs = srv.observer.classify(okey, status, rhdrs, obs_body,
                                                expected_model=expected)
                    srv.observer.record(obs, count_usage=False)
                    if obs.failover:  # 429/402/503/404/401+billing = exhausted → fail over
                        if obs.exhausted:  # account-level exhaustion → cool the
                            srv.set_cooldown(route, obs.retry_after)  # provider (R10c);
                        # a 404 ("model gone") is model-level — do NOT cool the provider.
                        if more:  # count only providers we actually move PAST
                            failovers.append({"provider": route.label, "status": status,
                                              "reason": obs.note or "exhausted"})
                            continue
                    # terminal capacity error, OR a 400/401/403 client/auth error we must
                    # NOT fail over (R6) — relay the real upstream response as-is.
                    self._send_resp_headers(status, ctype, route.label, failovers, False)
                    self._write(body_bytes)
                    srv.note_request(requested, route.label, status, 0.0, failovers)
                    return

                # ---- 200, non-streaming: buffer, then check for a silent downgrade ----
                if not is_stream:
                    body_bytes = self._drain(resp)
                    observed = _extract(body_bytes, ctype)
                    obs = srv.observer.classify(okey, 200, rhdrs, observed, expected_model=expected)
                    if obs.pseudo_success and more:  # downgrade + alternatives → fail over
                        srv.observer.record(obs, count_usage=False)
                        failovers.append({"provider": route.label, "status": 200,
                                          "reason": obs.note})
                        continue
                    srv.observer.record(obs, count_usage=True)  # served → bill usage (R10a)
                    # ── post-response hooks ──────────────────────────
                    cost = obs.usage.cost_usd if obs.usage else 0.0
                    if srv.response_normalizer is not None:
                        body_bytes = srv.response_normalizer.normalize(
                            body_bytes.decode(errors="replace"),
                            NormalizeMode.STANDARDIZE_MD,
                        ).encode()
                    if srv.semantic_cache is not None:
                        cache_key = hashlib.sha256(raw_body).hexdigest()
                        srv.semantic_cache.set(cache_key, body_bytes,
                                               rhdrs, ttl=3600)
                    if srv.quality_scorer is not None:
                        srv.quality_scorer.record(
                            route.label, 0, success=True, tokens=0)
                    if srv.spend_limiter is not None and cost > 0:
                        srv.spend_limiter.record(cost)
                    self._send_resp_headers(200, ctype, route.label, failovers, obs.pseudo_success)
                    self._write(body_bytes)
                    srv.note_request(requested, route.label, 200, cost, failovers)
                    return

                # ---- 200, streaming: buffer the head until `model` is seen (or a cap),
                #      so we can fail over a downgrade BEFORE committing bytes (R1) ----
                head: list[bytes] = []
                head_bytes = 0
                stream_broke = False
                try:
                    while head_bytes < _STREAM_HEAD_CAP:
                        c = resp.read(8192)
                        if not c:
                            break
                        head.append(c)
                        head_bytes += len(c)
                        if _extract(b"".join(head), ctype).get("model"):
                            break
                except Exception:  # upstream dropped/garbled before we committed any byte
                    stream_broke = True
                if stream_broke:  # nothing sent yet → treat like a failed attempt, fail over
                    srv.observer.record(srv.observer.classify(okey, 503, {}, {},
                                        expected_model=expected), count_usage=False)
                    if more:
                        failovers.append({"provider": route.label, "status": "stream-error",
                                          "reason": "upstream stream interrupted"})
                        continue
                    self._send_resp_headers(502, "application/json", route.label, failovers, False)
                    self._write(json.dumps(
                        {"error": {"message": "upstream stream failed"}}).encode())
                    srv.note_request(requested, route.label, "stream-error", 0.0, failovers)
                    return

                obs = srv.observer.classify(okey, 200, rhdrs, _extract(b"".join(head), ctype),
                                            expected_model=expected)
                if obs.pseudo_success and more:  # downgrade detected pre-commit → fail over
                    srv.observer.record(obs, count_usage=False)
                    failovers.append({"provider": route.label, "status": 200, "reason": obs.note})
                    continue
                # commit: stream the buffered head + the remainder (headers now sent —
                # a later read error can only truncate, never fail over).
                self._send_resp_headers(200, ctype, route.label, failovers, obs.pseudo_success)
                full = list(head)
                ok = all(self._write(c) for c in head)
                try:
                    while ok:
                        c = resp.read(8192)
                        if not c:
                            break
                        full.append(c)
                        ok = self._write(c)
                except Exception:
                    pass  # headers committed; partial stream is unavoidable
                served_obs = srv.observer.classify(okey, 200, rhdrs,
                                                   _extract(b"".join(full), ctype),
                                                   expected_model=expected)
                srv.observer.record(served_obs, count_usage=True)
                cost = served_obs.usage.cost_usd if served_obs.usage else 0.0
                srv.note_request(requested, route.label, 200, cost, failovers)
                return
            finally:
                try:  # release the upstream socket/fd promptly (don't lean on GC)
                    resp.close()
                except Exception:
                    pass
            return


class GatewayProxyServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """A loopback OpenAI-compatible proxy in front of one or many upstreams.

    Single-upstream: pass ``upstream_base`` + ``api_key``. Multi-provider pools
    (failover across providers): pass ``routes`` mapping the agent-facing model id
    to its ``UpstreamRoute`` (base, key, optional upstream model-id rewrite); the
    single upstream, if also given, is the fallback."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        upstream_base: str | None = None,
        api_key: str | None = None,
        observer: GatewayProxy | None = None,
        routes: dict[str, UpstreamRoute] | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
        fwd_timeout: float = 180.0,
        strip_v1: bool = True,
        token: str | None = None,
        model_ids: list[str] | None = None,
        pools: dict[str, list[UpstreamRoute]] | None = None,
        model_meta: dict[str, dict] | None = None,
        max_body_bytes: int = 10 * 1024 * 1024,
        default_cooldown: float = 60.0,
        failover_log_path: str | None = None,
        guardrails: Guardrails | None = None,
        semantic_cache: SemanticCache | None = None,
        response_normalizer: ResponseNormalizer | None = None,
        observability: Observability | None = None,
        quality_scorer: QualityScorer | None = None,
        spend_limiter: SpendLimiter | None = None,
        request_inspector: RequestInspector | None = None,
        session_affinity: SessionAffinity | None = None,
        speculative_executor: SpeculativeExecutor | None = None,
        consensus_router: ConsensusRouter | None = None,
        virtual_key_manager: VirtualKeyManager | None = None,
        policy_router: PolicyRouter | None = None,
    ) -> None:
        super().__init__((host, port), _ProxyHandler)
        self.upstream_base = upstream_base
        self.api_key = api_key
        self.routes = routes or {}
        self.observer = observer or GatewayProxy()
        self.fwd_timeout = fwd_timeout
        self.strip_v1 = strip_v1
        # Anti-DNS-rebinding: when bound to loopback, only accept requests whose Host
        # header is a loopback literal — a rebound attacker domain (Host: evil.com) is
        # rejected, so a malicious web page can't drive the ungated-loopback gateway
        # (security review HIGH). A non-loopback (tokened) bind relies on the token.
        self.require_loopback_host = is_loopback(host)
        # Gateway mode (ADR-0005 P1): a bearer token (None = open) and the
        # agent-facing model ids to serve at /v1/models (None = don't intercept).
        self.token = token
        self.model_ids = model_ids
        # Per-model metadata surfaced in /v1/models (context_window, max_tokens,
        # reasoning, vision, audio) — optional, never carries secrets.
        self.model_meta = model_meta or {}
        # P2 failover: model id → ordered (cost-ranked) candidate chain; a
        # provider-keyed cooldown with Retry-After expiry (R7/R10c); and a bounded
        # in-memory failover event log (+ optional JSONL file) for visibility (D3).
        self.pools = pools or {}
        self.max_body_bytes = max_body_bytes
        self.default_cooldown = default_cooldown
        self.failover_log_path = failover_log_path
        self.guardrails = guardrails
        self.semantic_cache = semantic_cache
        self.response_normalizer = response_normalizer
        self.observability = observability
        self.quality_scorer = quality_scorer
        self.spend_limiter = spend_limiter
        self.request_inspector = request_inspector
        self.session_affinity = session_affinity
        self.speculative_executor = speculative_executor
        self.consensus_router = consensus_router
        self.virtual_key_manager = virtual_key_manager
        self.policy_router = policy_router
        self._cooldown: dict[str, float] = {}
        self._cooldown_lock = threading.Lock()
        self.failover_events: collections.deque[dict] = collections.deque(maxlen=200)
        # per-provider counters for the console (P4): label → served/failed/cost.
        self.provider_stats: dict[str, dict] = {}
        # Optional web-setup write handler (Setup phase): callable(action, payload) ->
        # (status, dict). None (default) keeps the console READ-ONLY. The gateway wires
        # this only for the user-config-dir flow; it writes config + reloads routes.
        self.setup_handler = None

    def route_for(self, model: str) -> UpstreamRoute | None:
        """Which upstream serves ``model``: an explicit route, else the single
        upstream fallback, else None (no route → 502)."""
        if model in self.routes:
            return self.routes[model]
        if self.upstream_base:
            return UpstreamRoute(self.upstream_base, self.api_key)
        return None

    def apply_routes(self, routes: dict, pools: dict, model_ids: list[str],
                     model_meta: dict[str, dict] | None = None) -> None:
        """Atomically swap the live routing config (web-setup hot-reload) under the
        same lock ``chain_for`` reads — so an in-flight request never sees a torn
        (mixed old/new) routes-vs-pools view (security review LOW)."""
        with self._cooldown_lock:
            self.routes = routes
            self.pools = pools
            self.model_ids = model_ids
            self.model_meta = model_meta or {}

    def chain_for(self, model: str) -> list[UpstreamRoute]:
        """The ordered failover chain for ``model``: a configured pool (multiple
        cost-ranked providers), else a single route/upstream (a chain of one), else
        ``[]`` (no route → 502). A 1-element chain never fails over — exactly the
        pre-P2 single-upstream behavior."""
        with self._cooldown_lock:  # paired with apply_routes → consistent snapshot
            if model in self.pools:
                return list(self.pools[model])
            if (self.policy_router is not None and model.startswith("policy/")):
                policy_name = model[len("policy/"):]
                return self.policy_router.resolve(policy_name, self.routes,
                                                  self.pools)
            single = self.route_for(model)
            return [single] if single is not None else []

    def order_by_cooldown(self, chain: list[UpstreamRoute]) -> list[UpstreamRoute]:
        """Try providers NOT in active cooldown first; keep cooled ones as a
        last resort so a stale cooldown never permanently blocks a request (R7)."""
        now = time.monotonic()
        with self._cooldown_lock:
            fresh = [r for r in chain if self._cooldown.get(r.upstream_base, 0.0) <= now]
            cooled = [r for r in chain if self._cooldown.get(r.upstream_base, 0.0) > now]
        return fresh + cooled

    def set_cooldown(self, route: UpstreamRoute, retry_after: int | None) -> None:
        """Mark a provider out-of-capacity until ``Retry-After`` (or a default),
        keyed by provider (upstream_base) — a 429 is account-level, so all of that
        provider's models are skipped, not just the one (R10c)."""
        secs = float(retry_after) if (retry_after and retry_after > 0) else self.default_cooldown
        with self._cooldown_lock:
            self._cooldown[route.upstream_base] = time.monotonic() + secs

    def note_request(self, model: str, served_by: str, status, cost: float,
                     failovers: list[dict]) -> None:
        """Account one finished request (called on EVERY exit path): bump the served
        provider's served/cost counters and each failed-over provider's failure
        counter (per-provider visibility, D3/P4), and — when failover happened —
        append a failover event (ring buffer + optional JSONL)."""
        def _slot(stats, label):
            return stats.setdefault(label, {"served": 0, "failed": 0, "errors": 0,
                                            "cost": 0.0, "last_status": None})
        with self._cooldown_lock:
            s = _slot(self.provider_stats, served_by)
            if status == 200:
                s["served"] += 1   # a real success
                s["cost"] += cost
            else:
                s["errors"] += 1   # terminal failure/relayed error — NOT a success (P4 review)
            s["last_status"] = status
            for f in failovers:
                fs = _slot(self.provider_stats, f["provider"])
                fs["failed"] += 1
                fs["last_status"] = f["status"]
            if failovers:
                self.failover_events.append(
                    {"model": model, "served_by": served_by, "status": status,
                     "failovers": list(failovers)})
        if failovers and self.failover_log_path:
            try:
                with open(self.failover_log_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(
                        {"model": model, "served_by": served_by, "failovers": failovers}) + "\n")
            except OSError:
                pass

    def status_snapshot(self) -> dict:
        """A JSON-able view for the console (P4): pool config, per-provider stats +
        cooldown, cumulative usage, and the recent failover events."""
        now = time.monotonic()
        with self._cooldown_lock:
            cooled = {base: round(t - now, 1) for base, t in self._cooldown.items() if t > now}
            stats = {k: dict(v) for k, v in self.provider_stats.items()}
            events = list(self.failover_events)
        pools = {vid: [r.label for r in chain] for vid, chain in self.pools.items()}
        for mid, r in self.routes.items():
            pools.setdefault(mid, [r.label])
        # map a provider label → seconds of cooldown remaining (via its base url)
        label_cooldown: dict[str, float] = {}
        for chain in list(self.pools.values()) + [[r] for r in self.routes.values()]:
            for r in chain:
                if r.upstream_base in cooled:
                    label_cooldown[r.label] = cooled[r.upstream_base]
        u = self.observer.cumulative_usage()
        return {
            "pools": pools,
            "providers": stats,
            "cooldown_seconds": label_cooldown,
            "usage": {"tokens_in": u.tokens_in, "tokens_out": u.tokens_out,
                      "cost_usd": round(u.cost_usd, 6)},
            "recent_failovers": events[-50:],
        }

    @property
    def url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        if isinstance(host, bytes):
            host = host.decode()
        return f"http://{host}:{port}"

    def serve_in_thread(self) -> threading.Thread:
        t = threading.Thread(target=self.serve_forever, daemon=True)
        t.start()
        return t
