# Rocinante (10.0.1.51) Recon — Read-Only

Date: 2026-07-06
Method: SSH via `~/.ssh/config` host alias `rocinante` (key `~/.ssh/mediastack`, `IdentitiesOnly yes`, `ProxyCommand` jumps through `stack@10.0.1.60` = the `mediastack` host). Connection succeeded, no brute-forcing needed.

## SSH ACCESS STATUS
- **Connected successfully** as `stack@rocinante` (hostname confirms `rocinante`).
- Key used: `~/.ssh/mediastack` (same key as the `mediastack` host at 10.0.1.60 — Rocinante is reached *through* that box via ProxyCommand, not directly routable/keyed on its own).
- No passwordless sudo (`sudo -n true` → "a password is required"). Root-only info (e.g. `ss -tlnp` process names, full listening-port owner detail) was not obtainable read-only; did not attempt further.

## IDENTITY
- Hostname: `rocinante`
- OS: Ubuntu 24.04.4 LTS (Noble Numbat)
- Kernel: 6.8.0-117-generic, x86_64
- Uptime: **34 days, 1h** — looks stable/always-on, not a throwaway box.

## RESOURCES
- CPU: 4 cores
- RAM: 7.6Gi total, 1.4Gi used, 6.1Gi available (healthy headroom)
- Swap: 4.0Gi (789Mi used)
- Disk: `/dev/sda2` 58G total, 26G used, 29G avail (48%) — plenty of room
- Coordinator-suitability: resource-wise this is a perfectly capable box (4 core / 8GB / SSD-class disk headroom), **but it is not idle** (see below).

## WHAT'S RUNNING — THIS IS NOT AN IDLE SPARE BOX
Rocinante is an **actively running SLOP/mediastack production-ish host**, not decommissioned hardware:

- `docker ps -a` shows **10 containers actively "Up 4 weeks (healthy)"** plus 1 exited `hello-world` test container:
  - `radarr`, `sonarr`, `sabnzbd`, `prowlarr` — full media-automation stack
  - `decypharr`, `filebrowser`, `komodo-ferretdb`, `komodo-periphery` — Komodo-managed infra + FerretDB
  - `stirling_pdf`, `bentopdf`, `dozzle` — PDF tools + docker log viewer
  - All containers on a custom bridge network named `mediastack` (this is why `docker ps` shows no published PORTS — internal network / reverse-proxied elsewhere, not exposed directly on the host).
- `systemctl` shows `mediastack.service` **loaded/active/running** as a first-class systemd service.
- A **GitHub Actions self-hosted runner is registered and live** in `~/actions-runner` (agent id 21, name "rocinante", pool "Default", targeting `https://github.com/Nnyan/mediastack`). This is a CI runner for the mediastack/SLOP repo — repurposing this box would silently kill that runner.
- `/opt/mediastack` is a live clone of `https://github.com/Nnyan/SLOP.git`, on branch `main`, up to date with origin, with 2 untracked local files (`.installer-state.json`, `.req_hash` — installer state, low risk but not upstream-committed).
- `/opt/ms`, `/opt/test-ms`, `/opt/stacks` exist (installer/catalog scaffolding, mostly empty/root-owned).

**Conclusion on ownership:** this is unambiguously a **SLOP/mediastack box**, not Charon-related. No `proxy.py`, no gateway artifacts, no Charon fingerprints found anywhere searched (home dir, `/opt`, `/srv`).

## DATA AT RISK IF REPURPOSED/CLEANED — BACK UP FIRST
All of the following live under **`/srv/mediastack/config/*`** (bind mounts) and named Docker volumes — none of this was touched, only inspected read-only:

| Container | Data location | What it is |
|---|---|---|
| radarr/sonarr/sabnzbd/prowlarr | `/srv/mediastack/config/{radarr,sonarr,sabnzbd,prowlarr}` | full app configs/DBs (indexers, download history, library state) |
| filebrowser | `/srv/mediastack/config/filebrowser` + 2 named docker volumes (`.../database`, `.../srv`) | filebrowser DB + served tree |
| decypharr | `/srv/mediastack/config/decypharr` + a named docker volume mounted at `/app` | app state |
| komodo-ferretdb | `/srv/mediastack/config/komodo/ferretdb` + named docker volume at `/state` | FerretDB (Mongo-compatible) data — likely Komodo's backing DB |
| komodo-periphery | `/var/lib/mediastack/komodo/periphery` + docker socket bind | Komodo agent state, has docker.sock access |
| stirling_pdf / bentopdf | `/srv/mediastack/config/{stirling_pdf,bentopdf}` | app configs |
| dozzle | `/srv/mediastack/config/dozzle` + docker socket bind | log-viewer config (low value) |
| all of radarr/sonarr/sabnzbd | `/mnt/media` (shared bind) | actual media library files — **check what's mounted at `/mnt/media` on the host, could be large/irreplaceable** |
| `/opt/mediastack` | 241M, git repo | installer/compose source — already pushed to GitHub, low risk but has 2 untracked local files |
| `/srv/mediastack` | 307M total configs | see table above |
| `~/actions-runner` | CI runner registration + `_work` dir | would need de-registration from GitHub (agent id 21) before decommission, or it'll show as a permanently-offline runner |

**Nothing was modified, stopped, or deleted.** `du -sh` and `docker inspect` are read-only and were the only "heavier" commands run.

## COORDINATOR PREREQS
- Python 3.12.3 present (`/usr/bin/python3`) ✓
- systemd 255 present ✓
- `avahi-daemon`: **not installed** (empty `dpkg -l | grep avahi`, `systemctl is-active` → inactive/not-found) — would need install if mDNS discovery is part of the coordinator design.
- Passwordless sudo: **NO** — any coordinator install/service work will require an interactive sudo password or a sudoers change first.

## SUMMARY

**SAFE TO REPURPOSE?** **No — not without a real migration plan.** This is a live, 34-day-uptime SLOP/mediastack host running 10 healthy containers, a systemd-managed mediastack service, and a registered GitHub Actions CI runner for `Nnyan/mediastack`. Treating it as a "spare old test box" would take down active media-automation infra and orphan a CI runner.

**DATA TO BACK UP FIRST:** `/srv/mediastack/config/*` (all app configs/DBs), the 3 named Docker volumes (filebrowser DB×2, decypharr app, ferretdb state), `/var/lib/mediastack/komodo/periphery`, and whatever is bind-mounted at `/mnt/media` (not yet inventoried — recommend a follow-up read-only pass with `df -h /mnt/media` and a top-level `ls`/`du` there before any decommission).

**SSH ACCESS STATUS:** Working, via jump through `mediastack` (10.0.1.60) using the shared `mediastack` key. No passwordless sudo.

**COORDINATOR-SUITABILITY:** Resource-wise (4 core/8GB/idle-CPU/29GB free disk) it would be an easy, capable coordinator host. Operationally it is currently a *different* production role. If repurposing is still desired, this needs to be an explicit decommission-and-migrate decision (move mediastack stack elsewhere or accept its loss, de-register the CI runner, back up the config/volume list above) — not a "just wipe it" cleanup.
