# Charon Fleet — Session Handoff (2026-07-02T06:35:00Z)

## Bootstrap (copy-paste into next session)

Read `/home/stack/charon-private/fleet/SESSION-HANDOFF.md` fully, then run
`bash /home/stack/charon-private/fleet/status.sh && bash /home/stack/charon-private/fleet/validate_board.sh`,
check the board for claimed names, register with an unused Jedi name + `repo="charon"`, then go.

---

## Auto-generated state

### Git
```
master — 3 new squash-merged PRs this session: #79 (WCI), #80 (WCI-FOLLOWON), #81 (PROD-INSTALL)
feat/global-fallback-provider — accumulated branch (needs rebase)
```

### Open PRs
```
(none)
```

### Gate
```
841 passed, ruff clean, mypy clean (pre-existing cli.py errors only), boundary/version clean
```

### Board
```
done: WCI, WCI-FOLLOWON, PROD-INSTALL, DSGN-WCI-PROOF
```

---

## Human analysis

**Session name:** `luke-skywalker`

### What was done

1. **PR #78 merged** — fixed gate failure (stale `test-hygiene` entry in `gates.json` on `feat/obs-ui`, cherry-picked fix `460b9e1`). Batched 15+ tickets.

2. **DSGN-WCI-PROOF §5.1 proof contract** — designed, adversarially reviewed (4 gaps found+fixed: decorator registrations, non-main configs, autouse fixtures, re-export chains), operator approved. Artifact: `/home/stack/charon-private/fleet/DSGN-WCI-5-1-PROOF.md`.

3. **WCI landed on master** (PR #79) — `feat/wci-mvp`: static reconciler + depth pre-sort.

4. **WCI-FOLLOWON built** (PR #80) — 4 changes:
   - `merge_after` edge on Unit/PlanUnit schema
   - `board.claimable` extended with certificate consumption (F1 invariant)
   - `engine/semantic_proof.py` — 4-signal independence analysis (S1 import, S2 symbol, S3 config, S4 test)
   - 18 tests in `test_semantic_proof.py`

5. **PROD-INSTALL built** (PR #81):
   - `charon update` subcommand (pipx/pip detection)
   - `charon doctor --gateway` preflight (probes `/v1/models`)
   - `install.sh` one-liner bootstrap (already complete from earlier)

### Remaining (all approved by operator, prompts authored)

| Ticket | Status | Owns | Key files |
|---|---|---|---|
| **TIER-RECS** | prompt written (`prompts/tier-recs.md`), need to author and build | `cli.py`, `recommend.py`, `config.py` | Phase B: LLM-judge tier ranking from live `/v1/models` |
| **UX-POLISH** | prompt needs authoring, owns expanded for web items | `cli.py`, `proxy_server.py`, templates | 7 remaining items (key validation, sys.argv[0], URL hints, docs, discoverability, token cookie) |
| **ATC** | blocked — adversarial audit of all committed work | none | Audit after all build work done |

### Next session

Continue building in optimized file-cluster order:
1. **CLI cluster** — TIER-RECS + UX-POLISH together (both touch `cli.py`, single PR)
2. **Web cluster** — UX-POLISH web items (`proxy_server.py` + templates)
3. **ATC** — adversarial audit
