# Stage 7-A: Roci root-backup + old SLOP decommission — 2026-07-07

Status: **COMPLETE, all steps succeeded, backup verified before decommission.**

## 1. Root-backup (remaining root-only bits)

- Command: `ssh rocinante 'sudo tar czf /tmp/roci-root-extras.tgz /srv/mediastack/config/traefik/acme*.json /var/lib/mediastack/komodo/periphery'` → exit 0 (only benign "Removing leading `/`" notices, no errors).
- Pulled to: `/home/stack/backups/roci-decommission/roci-root-extras.tgz` (3723 bytes).
- **Verify — `tar tzf` contents:**
  ```
  srv/mediastack/config/traefik/acme-buypass.json
  srv/mediastack/config/traefik/acme.json
  srv/mediastack/config/traefik/acme-zerossl.json
  var/lib/mediastack/komodo/periphery/
  var/lib/mediastack/komodo/periphery/ssl/
  var/lib/mediastack/komodo/periphery/ssl/cert.pem
  var/lib/mediastack/komodo/periphery/ssl/key.pem
  ```
- **acme*.json**: all three are **0 bytes** on Roci itself (`ls -la` confirmed, root-owned `mediastack:mediastack`, mode 600) — never had real certs issued (no public DNS/domain hit this box), so the empty archive entries are correct/expected, not a backup failure.
- **komodo/periphery**: `sudo find -maxdepth 2 -type f` → `ssl/cert.pem`, `ssl/key.pem` only; `du -sh` → 16K total. **This is a real TLS keypair** (periphery agent's own cert+key, used for Komodo core↔periphery mTLS) — now preserved in the archive. Not an external-service credential, but worth having if periphery is ever re-paired without regenerating trust.
- Combined with the already-existing `/home/stack/backups/roci-decommission/mediastack-config.tgz` (23M, 1994 entries, verified in a prior pass), **all root-owned and user-owned state on Roci is now backed up.** Backup gate: PASS.

## 2. Decommission

- **Compose stack**: project name was `compose` (not `/opt/mediastack` — that dir holds the git checkout with `docker-compose.yml`/`docker-compose.dev.yml`, but the actually-running project's compose files live at `/var/lib/mediastack/compose/*.yaml`, confirmed via `sudo docker compose ls`). Ran `ssh rocinante 'sudo docker compose -p compose down'` → **exit 0**. All 11 containers (dozzle, filebrowser, decypharr, komodo-ferretdb, stirling_pdf, bentopdf, sabnzbd, prowlarr, radarr, sonarr, komodo-periphery) stopped, removed, and network `compose_default` removed. **Volumes were NOT touched** (no `-v` flag used) — data-on-disk safety net intact per instructions.
- **Service**: `ssh rocinante 'sudo systemctl disable --now mediastack.service'` → exit 0, output `Removed "/etc/systemd/system/multi-user.target.wants/mediastack.service"`. `systemctl is-enabled mediastack.service` now reports `disabled`.
- **GH Actions runner**: `~/actions-runner/svc.sh status` → literal output **"not installed"** (no systemd service was ever installed for it on this box; confirmed also via `systemctl list-units --all "actions.runner*"` → 0 units). Nothing to uninstall — matches the recon in `rocinante-verify.md` (runner process dead since 2026-06-26, no service). Registration file (`~/actions-runner/.runner`) still shows `agentName: rocinante`, `agentId: 21`, registered against the old pre-migration URL `https://github.com/Nnyan/mediastack` (pool "Default"). Per instructions, left as-is — an offline/unregistered-service runner entry is harmless and `gh api` already confirmed (prior pass) it doesn't show up in either the old repo's or the current org's live runner list.

## 3. Quiescent verification

- `sudo docker ps -a` → **no mediastack containers at all** (stopped+removed, not just exited). Only unrelated pre-existing container present: `determined_thompson` (Exited (0) 2 weeks ago) — not part of mediastack, not touched, noted for completeness only.
- `systemctl is-enabled mediastack.service` → `disabled` (confirmed).
- `df -h /` → 58G total, **26G used, 30G avail (47%)** — essentially unchanged from the pre-decommission 29G-avail baseline, as expected since only containers were removed, not images/volumes (data-on-disk safety net preserved per instructions).
- `free -h` → 7.6Gi total mem, 676Mi used, 6.9Gi available — box is idle/light, healthy.
- `python3 --version` → **Python 3.12.3** — present, ready for next stage.
- `systemctl --version` → **systemd 255** — present.

## Explicitly NOT done (per instructions)
- No image/volume removal (`docker compose down -v` was NOT used).
- `/srv/mediastack` and all volumes left on disk untouched.
- No deploy of the Charon bridge coordinator.
- No GitHub runner de-registration forced (left as harmless offline entry).

## Bottom line
Backup gate passed (root-extras + prior config tarball both verified non-empty/correct), decommission completed cleanly (containers/network removed, service disabled, no runner service to uninstall), box verified quiescent with Python 3.12.3 + systemd 255 present and ~30G free disk / ~6.9Gi free mem — **Roci is ready for the next stage (Charon bridge coordinator deploy).**
