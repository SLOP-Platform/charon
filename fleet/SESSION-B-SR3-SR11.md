# DeepSeek build session B — implement SR-3 then SR-11

You are a Charon build session. Repo: `/home/stack/code/charon`. Implement tickets **SR-3 then SR-11**, in that order.

## 1. Ground yourself first (read these)
- `/home/stack/code/charon/AGENTS.md` — standing orders (mandatory)
- `/home/stack/charon-private/fleet/WORKFLOW.md` — claim / build / gate / commit process

## 2. The tickets — read the board + prompt file for each
1. **SR-3** — SemanticCache hit/miss stats + keep exact-match keying (document that fuzzy/semantic matching is unsafe for code).
   - `/home/stack/charon-private/fleet/board/SR-3.md`
   - `/home/stack/charon-private/prompts/sr-3.md`
   - `owns:` `src/charon/cache.py`, `tests/test_cache.py`
2. **SR-11** — add `.github/dependabot.yml` for `github-actions` version bumps (PR-only, SHA-pin preserving). **Use the exact YAML in the prompt file.**
   - `/home/stack/charon-private/fleet/board/SR-11.md`
   - `/home/stack/charon-private/prompts/sr-11.md`
   - `owns:` `.github/dependabot.yml` (one new file, nothing else)

## 3. Rules — non-negotiable
- Do each ticket on **its own git worktree off the latest `feat/prod-install`**, on the branch in the ticket's `branch:` field.
- Touch **ONLY** the files in that ticket's `owns:` line. If you need a file outside `owns:`, **STOP and flag it** — do not create or edit it (that's another ticket's file).
- Before committing, the **FULL gate must be green**:
  ```
  PYTHONPATH=src python3 -m pytest -q && ruff check src tests tools && mypy src/charon && python3 tools/check_boundary.py src && python3 tools/check_version.py
  ```
- Commit each ticket with a conventional message (e.g. `feat(SR-3): …`).
- **Do NOT push and do NOT open a PR.** Stop after committing — a Claude reviewer + the operator gate the merge.

When both are committed, report the branch names + final `pytest` counts and stop.
