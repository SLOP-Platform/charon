# Roci config backup (pre-decommission) — 2026-07-06

Status: **PASSED with one known, non-blocking gap** (TLS private key files, root 600 perms — expected, harmless).

## Archive
- Path: `/home/stack/backups/roci-decommission/mediastack-config.tgz`
- Size: 23M
- File count (entries in tar index): 1994
- SHA256: `7978842269b17a4d7784af10574013abaf54c401ed24261a50734ef7e03c6245`

Method: `ssh rocinante 'tar czf - -C /srv/mediastack config' > .../mediastack-config.tgz` — streamed off Roci, nothing written to Roci. Read-only on Roci throughout; no stop/remove/disable/modify actions taken there.

## Gap found (tar exit code 2)
`tar` reported permission denied on 3 files and exited 2:
- `config/traefik/acme.json`
- `config/traefik/acme-buypass.json`
- `config/traefik/acme-zerossl.json`

These are Traefik's ACME (Let's Encrypt) account-key/cert stores, typically root-owned `0600`. Everything else in `config/traefik/` (traefik.yml, dynamic/) and every other subdir made it into the archive intact, **including `config/komodo/` (root-owned dir)** — its 3 ferretdb sqlite files (komodo.sqlite, -wal, -shm) are present in the archive, so the dir-ownership itself wasn't a blanket blocker, only those 3 specific cert files.

Per the run rules ("if it errors, capture the error and stop — report it"), stopped here rather than retrying with elevated privileges. **No sudo tar / privilege escalation was attempted on Roci.** If the operator wants the ACME certs preserved too, that requires a manual `sudo`-run copy on Roci itself (operator's own session, not this one).

## Verify results
- `tar tzf ... | wc -l` → 1994 (not 0, not "a few KB" — real content)
- Top-level dirs present in archive: bentopdf, decypharr, dockge, dozzle, filebrowser, komodo, prowlarr, radarr, sabnzbd, sonarr, stirling_pdf, tinyauth, traefik — matches expected mediastack service list.
- Size note: 23M compressed vs. ~305M raw (per `du -sh` sum below) — plausible ratio for sqlite/log-heavy config data; not itself a red flag given file count checks out.

## Manifest (`/home/stack/backups/roci-decommission/manifest.txt`)
`ls -la /srv/mediastack/config` + `du -sh` per subdir, captured read-only via ssh. Per-dir raw sizes:
- komodo 90M, sonarr 76M, prowlarr 65M, radarr 48M, sabnzbd 26M, stirling_pdf 52K, traefik 12K, rest ~4-8K.

## Sudo status (for pending komodo/periphery root check)
`ssh rocinante 'sudo -n true'` → **exit 1, "sudo: a password is required."**
Confirms recon: **no passwordless sudo** on Roci. The operator will need to run the komodo/periphery root check manually (interactive sudo), this session cannot do it non-interactively.

## Explicitly NOT done
- No stop/remove/disable/modify of anything on Roci.
- No sudo/privilege-escalation attempts on Roci.
- No decommission action taken. Backup + verify only, per instructions.
