# Rocinante (10.0.1.6x, host `rocinante`) — read-only verification pass

Date of pass: 2026-07-06 (read-only, no state changed)

## 1. Is the SLOP on Roci actually OLD/behind?

**Yes — decisively.**

- `/opt/mediastack` HEAD: commit `c3316bd6b77783d43e8f7f28a53e8084a96b83bb`, authored **Fri Jun 19 2026 11:47:00 -0700** ("publish: derived from e1b1e12 via make_public.py").
- `git status`: clean except two untracked scratch files (`.installer-state.json`, `.req_hash` — installer bookkeeping, not real changes).
- `git remote -v`: `origin https://github.com/Nnyan/SLOP.git` — this is the **old pre-org-migration repo name/lineage**. `Nnyan/SLOP` now redirects to `SLOP-Platform/SLOP`, which is a **different repo** than the current active one, `SLOP-Platform/mediastack` (created 2026-04-28, pushed as recently as **2026-07-07T04:00Z**, HEAD `de5c3e0d...` "fix(wizard): expose ollama_deploy step in API"). Roci's checkout isn't just behind — it's on a disconnected/superseded remote entirely, so a direct git ahead/behind diff isn't even possible (404 on compare).
- Running containers confirm the same story — every service was created **2026-05-23** and has been "Up 4 weeks" with no restarts/updates since:
  - dozzle, filebrowser, decypharr, komodo-ferretdb, stirling_pdf, bentopdf, sabnzbd, prowlarr, radarr, sonarr, komodo-periphery — all `Created` 2026-05-23 00:11–15:16 UTC, all still on `:latest`/pinned tags pulled at that time (per `docker system df -v`, image pull dates 6–9 weeks ago).
  - Meanwhile current SLOP-Platform/mediastack has commits landing same-day as this check (2026-07-07).

**Conclusion: Roci is running a deployment frozen ~6 weeks ago, tracking a defunct repo lineage. Confirmed stale/superseded.**

## 2. CI runner status

- Roci's local runner registration file (`~/actions-runner/.runner`) shows it was registered as **"rocinante"** against `https://github.com/Nnyan/mediastack` (also an old/pre-migration URL).
- `gh api repos/Nnyan/mediastack/actions/runners` → `{"total_count":0,"runners":[]}` (repo itself now redirects to `SLOP-Platform/mediastack`; no runner named rocinante shows up there either).
- `gh api orgs/SLOP-Platform/actions/runners` (the real, current org-level runner pool) → **3 runners: `4-lom`, `4-lom-2`, `4-lom-3`, all `status: online`**. No `rocinante` runner present.
- On-box evidence the runner process is **not currently running**: no `actions.runner.*` systemd unit exists, no runner process in `ps aux` (only unrelated `s6-supervise` docker/s6 processes), no crontab keeping it alive.
- Last runner diag log (`Runner_20260625-122935-utc.log`) ends **2026-06-26 02:36 UTC** with the runner losing its broker connection and the in-flight job being **Canceled** — i.e. it dropped off around the same time the git repo was last touched (Jun 19–26) and was never restarted.

**Conclusion: the Roci runner is already effectively dead/deregistered and has been for ~10 days. All current CI capacity for SLOP-Platform runs on the separate 4-LOM pool (`4-lom`, `4-lom-2`, `4-lom-3`, all online). Repurposing Roci removes zero live CI capacity — there is nothing to de-register; it's already not contributing.**

## 3. What is Roci-ONLY (would be lost on wipe)?

`/srv/mediastack/config/*` (du -sh, all bind mounts — these are real *arr state/DBs):
| dir | size |
|---|---|
| komodo | 90M |
| prowlarr | 65M |
| sonarr | 76M |
| radarr | 52M |
| sabnzbd | 26M |
| stirling_pdf | 52K |
| filebrowser | 8.0K |
| bentopdf/decypharr/dozzle/dockge/tinyauth | 4.0K each (empty/near-empty) |
| traefik | 12K |

Total ≈ **~310MB** of config/state — small, easy to back up in full (tar the whole `/srv/mediastack/config` tree).

**Named Docker volumes** — all trivially small, no real data:
- 7 local volumes, largest is 65.5KB (`ede78f8...` = filebrowser's sqlite db). Everything else is single-digit KB or 0B. These back filebrowser (`/srv`, `/database`), decypharr (`/app`), komodo-ferretdb (`/state`). Nothing volume-based is a meaningful data store beyond the bind-mounted `/srv/mediastack/config`.

**`/var/lib/mediastack/komodo/periphery`** — could not inventory: `Permission denied` as the `stack` user (no passwordless sudo available, per task constraints, so this was not forced). It's bind-mounted into `komodo-periphery` as `/etc/komodo` — by convention this is just periphery's small TOML config + keys, not a data store, but **this one directory's size/contents are unverified** and should be spot-checked with sudo (or by whoever has root) before wipe, since it may contain credentials/keys worth preserving even if tiny.

**`/mnt/media` — THE key finding.**
- `df -h /mnt/media` → falls through to `/dev/sda2` (the 58GB root disk, 26G used / 29G free). No dedicated filesystem.
- `ls -la /mnt/media` → **empty directory** (just `.` and `..`, 4096 bytes, nothing in it).
- `findmnt /mnt/media` → no output (not a mount point at all).
- `/proc/mounts` → no `media` entry.

**`/mnt/media` is not mounted, not a network/NFS share, and not a local media library — it is a bare empty directory living on the 58GB root disk.** This directory is bind-mounted into filebrowser/sabnzbd/radarr/sonarr as `/data`, but there's nothing in it. **This resolves the previously-flagged "un-inventoried /mnt/media" concern: there is no media library on Roci, local or remote, to lose.** (The actual media library must live elsewhere — presumably BB-8 or a separate NAS not touched by this pass.)

Root disk overall: 58GB total, 26G used, 29G free — consistent with "just the OS + docker images + small config," no large media payload anywhere on the box.

## 4. Uncommitted work / anything unusual

- Git: clean (2 untracked installer-bookkeeping files only, not real work).
- Home dir (`~stack`) is clean: only `actions-runner/` (the GH runner install, standard files), `setup-runner-rocinante.sh` (the original runner setup script — expected artifact, not "stray"), and normal dotfiles/caches. No ad-hoc scripts, no second project checked out.
- `find /opt /srv ~ -name .git` → only `/opt/mediastack/.git`. No other repos on the box.
- `crontab -l` → **no crontab for stack** (nothing scheduled).
- No systemd units for anything runner-related still installed.

Nothing unusual or irreplaceable found outside the two locations already covered above (`/srv/mediastack/config`, and the unverified-but-small `komodo/periphery`).

---

## IS ROCI SUPERSEDED? (yes/no + evidence)

**YES.** Git HEAD is 6+ weeks old and points at a defunct pre-migration remote (`Nnyan/SLOP` → `SLOP-Platform/SLOP`, not the active `SLOP-Platform/mediastack`); every running container was deployed 2026-05-23 and hasn't restarted/updated since; the box's own GH Actions runner disconnected 2026-06-26 and was never revived, while the org's actual CI pool (`4-lom`/`4-lom-2`/`4-lom-3`) is live and online today.

## SAFE TO REPURPOSE AFTER BACKING UP:
- `tar` up `/srv/mediastack/config/` in full (~310MB — komodo 90M, prowlarr 65M, sonarr 76M, radarr 52M, sabnzbd 26M, rest negligible). This is the only nontrivial state on the box.
- Snapshot/copy `/var/lib/mediastack/komodo/periphery` (small, permission-denied as non-root — grab it with sudo/root before wipe just in case it holds keys).
- (Optional, cheap) note the 7 docker volume IDs/names in this file in case any app-specific default needs re-seeding — but none contain meaningful data (all <66KB).

## BLOCKERS: none found.
- **CI runner**: not a blocker — Roci's runner is already dead/deregistered; current CI runs entirely on the separate 4-LOM pool.
- **Media library**: not a blocker — `/mnt/media` is empty and unmounted; no media data lives on Roci.
- **Unique data**: not a blocker — everything Roci-only is the ~310MB of *arr config under `/srv/mediastack/config`, fully backup-able with a single tar, plus the small unverified `komodo/periphery` dir worth a root-level spot check first.

No destructive action was taken; nothing on Roci or any other host was modified, stopped, or de-registered during this pass.
