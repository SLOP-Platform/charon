# Mode-A fresh-install dogfood — 4-LOM gateway + non-Claude clients (opencode, oh-my-pi)

GOAL: prove a TRUE fresh Charon install (docker, on 4-LOM 10.0.1.60) serves models, is reachable
from the operator PC over the LAN, and that non-Claude clients (oh-my-pi, opencode) route their LLM
calls through it. Human-driven (Mode A); the autonomous `charon work` loop is deferred.

## Phase 0 — stop the other gateway (avoid two-gateway confusion)
On .3.91:  `pkill -f "charon gateway"`   (restart later with:
`nohup charon gateway --host 0.0.0.0 --token f77ffd3b920f65b642238333a3d88f0e >/tmp/charon-gw.log 2>&1 &`)

## Phase 1 — fresh gateway on 4-LOM (run on 4-LOM, in the charon repo dir)
1. LAN bind — flip the gateway's host port from loopback to all-interfaces (still token-gated):
   ```
   sed -i 's|127\.0\.0\.1:8080:8080|8080:8080|' docker-compose.yml && grep -n '8080:8080' docker-compose.yml
   ```
   (only the gateway's 8080 line changes; the `charon-service` 8473 loopback line is untouched.)
2. Wipe + fresh:
   ```
   docker compose down -v
   export CHARON_GATEWAY_TOKEN=$(openssl rand -hex 16); echo "CHARON_GATEWAY_TOKEN=$CHARON_GATEWAY_TOKEN" > .env
   docker compose run --rm gateway setup      # pick opencode-zen; serve gpt-5.4 (+ others)
   docker compose up -d
   echo "TOKEN: $CHARON_GATEWAY_TOKEN"         # record it
   ```
3. Local check: `curl -s http://127.0.0.1:8080/v1/models -H "Authorization: Bearer $CHARON_GATEWAY_TOKEN"` → model list.
4. Firewall: ensure 8080 is open on the LAN (e.g. `sudo ufw allow 8080/tcp` if ufw is on).

## Phase 2 — reach it from the operator PC
- `curl http://10.0.1.60:8080/v1/models -H "Authorization: Bearer <token>"` → model list = LAN OK.
- Browser: `http://10.0.1.60:8080/` → live console (watch the `served` counter during the next phases).

## Phase 3 — oh-my-pi (the oh-my-pi test) — on the PC, charon CLI installed
- `charon connect omp --host 10.0.1.60 --port 8080 --token <token> --install`
  (installs omp if missing; writes `~/.omp/agent/models.yml` at the 4-LOM gateway; verifies first.)
- WATCH for the Windows-vs-WSL PATH gap (the prior friction) — note if `--install` handles it.
- Launch omp, send a prompt → confirm the 4-LOM console `served`/tokens rise = omp→Charon works.

## Phase 4 — opencode (second client cross-check) — on the PC
- `charon connect opencode --host 10.0.1.60 --port 8080 --token <token>`
- Set opencode default model to a Charon-served id; send a prompt → console counter rises.

## Phase 5 — "work a ticket" in Mode A (human-driven, non-Claude agent)
- Hand the agent the grounding doc (`GROUNDING-CHARON.md` for a Charon ticket, `GROUNDING-SLOP.md`
  for a SLOP ticket) + one real ticket's goal + accept check, in a repo clone.
- Let the non-Claude agent implement it; run the `accept:` check by hand. Success = check passes,
  with the agent's LLM having routed through Charon (console counter rose).

## Success criteria
fresh gateway serves models ✓ · LAN-reachable from PC ✓ · oh-my-pi routes via Charon ✓ · opencode
routes via Charon ✓ · a ticket worked + its accept check passes ✓. Feed the omp result back into
the OHMYPI-ASSESS ticket (client-only vs can-drive-charon-work).
