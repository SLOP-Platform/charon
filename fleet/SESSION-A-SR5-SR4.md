# DeepSeek build session A — implement SR-5 then SR-4

You are a Charon build session. Repo: `/home/stack/code/charon`. Implement tickets **SR-5 then SR-4**, in that order.

## 1. Ground yourself first (read these)
- `/home/stack/code/charon/AGENTS.md` — standing orders (mandatory)
- `/home/stack/charon-private/fleet/WORKFLOW.md` — claim / build / gate / commit process

## 2. The tickets — read the board + prompt file for each
1. **SR-5** — provider pricing capture (so `usage.cost_usd` isn't always 0).
   - `/home/stack/charon-private/fleet/board/SR-5.md`
   - `/home/stack/charon-private/prompts/sr-5.md`
   - `owns:` `src/charon/config.py`, `src/charon/discover.py`, `src/charon/providers.py`
2. **SR-4** — `SMART-ROUTING.md` doc corrections (mark speculative/consensus "not wired"; fix §1/§5/§8; note the §9 CLI commands that don't exist).
   - `/home/stack/charon-private/fleet/board/SR-4.md`
   - `/home/stack/charon-private/prompts/sr-4.md`
   - `owns:` the doc named in the ticket

## 3. Rules — non-negotiable
- Do each ticket on **its own git worktree off the latest `feat/prod-install`**, on the branch in the ticket's `branch:` field.
- Touch **ONLY** the files in that ticket's `owns:` line. If you need a file outside `owns:`, **STOP and flag it** — do not create or edit it (that's another ticket's file).
- Before committing, the **FULL gate must be green**:
  ```
  PYTHONPATH=src python3 -m pytest -q && ruff check src tests tools && mypy src/charon && python3 tools/check_boundary.py src && python3 tools/check_version.py
  ```
- Commit each ticket with a conventional message (e.g. `feat(SR-5): …`).
- **Do NOT push and do NOT open a PR.** Stop after committing — a Claude reviewer + the operator gate the merge.

When both are committed, report the branch names + final `pytest` counts and stop.
