#!/usr/bin/env bash
# ROLLBACK the 2026-07-10 opencode-go cheap-first / opencode-zen-deactivate change
# on the live Charon gateway (4-lom 10.0.1.60, container charon-gateway-1).
# Restores pools.json + models.json + providers.json from the pre-change backups,
# then triggers a setup-API write so the running gateway hot-reloads (NO restart).
# Reverts: the 4 opencode-go leg cost_ranks (back to 40/1000) and the 5 pool member
# lists (re-adds the opencode-zen bare-id legs, removes the opencode-go legs).
set -euo pipefail
SSH="ssh -i $HOME/.ssh/4lom stack@10.0.1.60"
TOK="b69323f986948a60f23699f2eb3fc787"
TS="20260710T010620Z"   # backup timestamp created before the change

read -r -d '' RELOAD <<'PYEOF' || true
import urllib.request, urllib.error, json
TOK="b69323f986948a60f23699f2eb3fc787"; BASE="http://127.0.0.1:8080/charon/"
def post(a,p):
    r=urllib.request.Request(BASE+a+"?token="+TOK,data=json.dumps(p).encode(),method="POST")
    r.add_header("Content-Type","application/json")
    try: x=urllib.request.urlopen(r,timeout=60); return x.status,json.loads(x.read().decode())
    except urllib.error.HTTPError as e: return e.code,e.read().decode()[:200]
# files are already restored on disk; this write triggers _reload() which re-reads them.
orig={
 "glm-5.2":["glm-5.2-ng","glm-5.2","glm-5.2-hf","glm-5.2-or","glm-5.2-nw","glm-5.2-cline"],
 "kimi-k2.6":["kimi-k2.6-ng","kimi-k2.6","kimi-k2.6-hf","kimi-k2.6-or","kimi-k2.6-nw","kimi-k2.6-cline"],
 "deepseek-v4-pro":["deepseek-v4-pro-ng","deepseek-v4-pro","deepseek-v4-pro-or","deepseek-v4-pro-ds","deepseek-v4-pro-cline"],
 "deepseek-v4-flash":["deepseek-v4-flash-ng","deepseek-v4-flash","deepseek-v4-flash-hf","deepseek-v4-flash-or","deepseek-v4-flash-ds","deepseek-v4-flash-cline"],
 "minimax-m3-free":["minimax-m3-free-ng","minimax-m3-free","minimax-m3-free-or","minimax-m3-cline"],
}
for pid,mem in orig.items(): print("reload pool",pid,post("pools",{"id":pid,"members":mem}))
PYEOF

# 1) restore the three config files from the pre-change backups
$SSH "docker exec charon-gateway-1 sh -c 'cd /data && cp -p pools.json.bak-opencode-$TS pools.json && cp -p models.json.bak-opencode-$TS models.json && cp -p providers.json.bak-opencode-$TS providers.json && echo restored'"
# 2) hot-reload the running gateway (re-reads the restored files)
echo "$RELOAD" | $SSH 'cat > /tmp/rlgo.py && docker cp /tmp/rlgo.py charon-gateway-1:/tmp/ >/dev/null && rm /tmp/rlgo.py && docker exec charon-gateway-1 python3 /tmp/rlgo.py && docker exec -u root charon-gateway-1 rm -f /tmp/rlgo.py'
echo "ROLLBACK COMPLETE (hot-reloaded, no restart)."
