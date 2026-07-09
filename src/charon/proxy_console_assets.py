"""Console/setup HTML assets for the gateway proxy (seam A).

Pure static data: the self-contained console, work panel, and setup pages
served by the observing proxy. Zero logic. Extracted verbatim from
proxy_server.py and re-exported there for the unchanged public import surface.
"""
from __future__ import annotations

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
    upstream_model:val('mups')||null,free:free};
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
