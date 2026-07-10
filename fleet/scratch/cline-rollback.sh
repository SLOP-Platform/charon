#!/usr/bin/env bash
# Rollback: fully un-wire Cline Pass from the live Charon gateway (hot-reload, NO restart).
# Reverses the 2026-07-09 cline-wire (5 pools + 6 models + provider). Idempotent-safe.
set -euo pipefail
SSH="ssh -i $HOME/.ssh/4lom stack@10.0.1.60"
TOK="b69323f986948a60f23699f2eb3fc787"
read -r -d '' PY <<'PYEOF' || true
import urllib.request,json,urllib.error
TOK="b69323f986948a60f23699f2eb3fc787"; BASE="http://127.0.0.1:8080/charon/"
def post(a,p):
    r=urllib.request.Request(BASE+a+"?token="+TOK,data=json.dumps(p).encode(),method="POST")
    r.add_header("Content-Type","application/json")
    try: x=urllib.request.urlopen(r,timeout=60); return x.status,json.loads(x.read().decode())
    except urllib.error.HTTPError as e: return e.code,e.read().decode()[:200]
# 1) restore the 5 pools to ORIGINAL members (drops the -cline leg)
orig={
 "glm-5.2":["glm-5.2-ng","glm-5.2-nw","glm-5.2-or","glm-5.2-hf"],
 "kimi-k2.6":["kimi-k2.6-ng","kimi-k2.6-nw","kimi-k2.6-or","kimi-k2.6-hf"],
 "deepseek-v4-pro":["deepseek-v4-pro-ng","deepseek-v4-pro-ds","deepseek-v4-pro-or"],
 "deepseek-v4-flash":["deepseek-v4-flash-ds","deepseek-v4-flash-ng","deepseek-v4-flash-or","deepseek-v4-flash-hf"],
 "minimax-m3-free":["minimax-m3-free-ng","minimax-m3-free-or"],
}
for pid,mem in orig.items(): print("pool",pid,post("pools",{"id":pid,"members":mem}))
# 2) remove the 5 cline model entries
for mid in ["glm-5.2-cline","kimi-k2.6-cline","deepseek-v4-pro-cline","deepseek-v4-flash-cline","minimax-m3-cline"]:
    print("rm model",mid,post("remove",{"kind":"model","name":mid}))
# 3) remove the cline-pass provider (leaves CLINE_PASS_API_KEY secret in place)
print("rm provider",post("remove",{"kind":"provider","name":"cline-pass"}))
# 4) remove the grok-4.3 frontier candidate (added same pass). gemini-3.1-pro was pre-existing -> left as-is.
print("rm pool grok-4.3",post("remove",{"kind":"pool","name":"grok-4.3"}))
for mid in ["grok-4.3-ng","grok-4.3-or"]:
    print("rm model",mid,post("remove",{"kind":"model","name":mid}))
PYEOF
echo "$PY" | $SSH 'cat > /tmp/rb.py && docker cp /tmp/rb.py charon-gateway-1:/tmp/ >/dev/null && rm /tmp/rb.py && docker exec charon-gateway-1 python3 /tmp/rb.py && docker exec -u root charon-gateway-1 rm -f /tmp/rb.py'
echo "ROLLBACK COMPLETE (hot-reloaded)."
# --- Disk-level fallback if the API rollback is unavailable ---
# Restores pre-wire config files, then any setup-API write hot-reloads them:
#   docker exec charon-gateway-1 sh -c 'cd /data && for f in providers pools models fallback; do cp -p $f.json.clinewire-20260709T043528Z.bak $f.json; done'
