# PROD-INSTALL — Production one-liner bootstrap installer

## Dependencies & sequence
**Wave: 3** (production-readiness, independent of all other tickets).
**depends_on: none.**

## Why
On Ubuntu 22.04 LTS (Python 3.10, no pip) a fresh user CANNOT follow the README `pipx install` line — they hit `No module named pip` and a too-old Python (Charon requires-python >=3.11). This is a real production-readiness barrier surfaced on charon-vm 2026-06-27.

## What to build

### 1. Harden `install.sh` into a one-liner bootstrap

```
curl -fsSL https://github.com/SLOP-Platform/charon/releases/latest/download/install.sh | bash
```

(or `wget -qO-` variant)

**Script behavior:**
- Detect OS/distro + package manager (apt/dnf/brew)
- Check for Python >=3.11, git, pip/pipx
- Install missing prereqs (escalate to sudo ONLY for package-manager step, with a clear prompt)
- If can't install, print the EXACT manual commands
- Install Charon via pipx (or venv fallback)
- Finish with next steps: gateway URL, web UI URL, how to point an app at Charon
- Idempotent (re-runnable for updates), preserves user config (`~/.charon`)
- Offer a "download → inspect → run" path in the README

**Pretty output (pure bash):**
- Colored section headers + bold key values (ANSI)
- Green ✓ / red ✗ status lines per prereq
- Step counters like `[2/5] Installing Python 3.11…`
- Auto-degrade to plain text when output is not a TTY or `NO_COLOR` set
- No ncurses, no Python `rich` — pure bash only, universal compatibility

### 2. `charon update` CLI subcommand

Thin wrapper that detects install method (pipx vs pip) and runs the correct upgrade command. Users conflate `setup`/`reset` (settings) with `update` (program) — clear separation needed.

### 3. `charon doctor` → gateway preflight

Extend `charon doctor` to probe the gateway (`GET /v1/models`) and report config status. Currently it only probes an ACP agent. Add a `--gateway` flag.

### 4. README/docs update

- Gateway vs orchestrator clarity per UX-POLISH item #8
- Docker group prerequisite note
- Install instructions with both one-liner and inspect-then-run paths

## Acceptance
- `install.sh` works on Ubuntu 22.04 (fresh), Ubuntu 24.04, macOS
- `charon update` subcommand works for pipx and pip installs
- `charon doctor --gateway` reports live gateway status
- Gate GREEN: ruff, mypy, boundary, version tests pass

## CONSTRAINTS
- Stdlib-only core. install.sh is bash-only (no Python deps).
- Product-clean (no SLOP/fleet/rig leak).
- install.sh hosted from GitHub release asset, not raw master.

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
