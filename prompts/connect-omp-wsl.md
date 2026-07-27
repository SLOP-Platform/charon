# CONNECT-OMP-WSL — fix `charon connect omp` (omp config schema + WSL install routing)

## Dependencies & sequence
**depends_on: OHMYPI-ASSESS** (the research must first determine omp 16.2.2's REAL custom-provider
config schema — see real-dep). Wave: after OHMYPI-ASSESS. **Owns `src/charon/connect.py` →
SERIALIZE with CLIENT-CONNECT-GUI** (which also owns `connect.py`); the two cannot run concurrently
— sequence them (either order). Disjoint from everything else.

## Why (live dogfood 2026-06-28, fresh 4-LOM Mode-A test)
`charon connect omp` has two real failures on WSL:
1. **The config omp gets is ignored.** It writes `~/.omp/agent/models.yml` with an inline `api_key`;
   omp (pi-coding-agent 16.2.2) does NOT consume it — `omp models` shows zero providers and
   `omp --model auto` falls back to its own OAuth sign-in. omp manages provider creds via a
   different mechanism (auth-broker / env / a different schema) that OHMYPI-ASSESS must pin down.
2. **`--install` installed to the wrong OS.** On WSL it used the **Windows** `bun` (via interop) →
   omp landed in `C:\Users\<u>\.bun\bin` (Windows), mismatching the WSL config it wrote → WSL `omp`
   not found. omp also needs **Bun ≥1.3.14** (not node) + `unzip`, which `--install` never set up.

## What to build
1. **Correct omp writer:** rewrite the omp config to the schema OHMYPI-ASSESS found omp actually
   reads (so `omp models` discovers the gateway and a completion works). Keep it agnostic — omp
   knowledge stays only in `connect.py`'s omp writer/registry entry.
2. **WSL-aware install:** detect WSL; for `--install` use a WSL-NATIVE package manager (don't shell
   out to a `bun`/`npm` that resolves to a Windows binary via interop), ensure the runtime omp needs
   (bun, unzip) is present or print a clear, correct manual recipe; verify the installed binary is
   on the WSL PATH and reads the WSL config you wrote. If a clean native install isn't possible,
   FAIL with an actionable message rather than silently installing to the wrong place.

## Acceptance
- `tests/test_connect_omp.py`: the omp writer emits the OHMYPI-ASSESS-confirmed schema (assert shape
  + that the gateway url/token land where omp reads them); WSL detection routes `--install` to a
  native manager (mock the platform + the installer call) and never to a Windows-interop binary;
  a clear error when native install is unavailable. Token never printed to stdout/logs.

## CONSTRAINTS
Own ONLY: `src/charon/connect.py`, `tests/test_connect_omp.py`. Stdlib core only; no secrets
committed. Gate GREEN every commit
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/CONNECT-OMP-WSL.md`. Draft PR, `submit.sh`,
STOP. BACKLOG (parked). Branch `feat/connect-omp-wsl`.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
