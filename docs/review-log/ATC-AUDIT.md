# ATC — Adversarial Technical/Code Audit

**Date:** 2026-07-02
**Gate:** 834 passed, ruff clean, mypy clean, boundary/version clean

## Summary

19 findings across 4 audit dimensions. 3 CRITICAL, 0 HIGH (but 2 mislabeled by reviewers — see reclassification below), 5 MEDIUM, 11 LOW/INFO.

---

## CRITICAL

### ATC-001: `_load_plan` silently drops `body` — agents receive empty ticket description

**Source:** Correctness review
**File:** `src/charon/cli.py:932-941`
**Severity:** CRITICAL

`_load_plan` constructs unit dicts from intake plan JSON but omits the `"body"` field. `PlanUnit.to_dict()` (`intake.py:264`) emits `"body": self.body`, but `_load_plan` drops it. The consumer path (`cli.py:949-956`) also misses body. Result: `Board.Unit.body = ""` everywhere, `_build_prompt()` receives `WorkUnit.body = ""`, and `if body:` at `acp.py:43` is False. **The agent never sees the full ticket description — only the one-line goal + accept commands.**

**Also:** `Board.Unit()` constructor at `cli.py:1280` doesn't pass `body=`.

**Fix:** Add `"body": u.get("body", "")` to both `_load_plan` paths. Pass `body=u.get("body", "")` in `Board.Unit(...)` call.

---

### ATC-002: Gateway startup prints raw token to stderr

**Source:** Security review
**File:** `src/charon/gateway.py:370-382`
**Severity:** CRITICAL

Gateway startup constructs `tq = f"?token={cfg.token}"` and prints it verbatim to stderr in console/setup URL lines. The raw bearer token appears in terminal output, shell history, and any log capture.

**Fix:** Mask the token (`?token=<REDACTED>`) or omit from URL output.

---

### ATC-003: `charon connect cline` prints raw token to stdout

**Source:** Security review
**File:** `src/charon/connect.py:411-412,526`
**Severity:** CRITICAL

The `cline` client's `launch` lambda interpolates `w.token` directly into user-facing output, and `run_connect` prints it unconditionally at line 526. Any `charon connect cline` leaks the gateway bearer token to stdout.

**Fix:** Replace literal token with `"<your-gateway-token>"` in guided instructions. Never print the literal token.

---

## HIGH

### ATC-004: CSRF bypass — both Origin and Sec-Fetch-Site absent

**Source:** Security review
**File:** `src/charon/proxy_server.py:569-577`
**Severity:** HIGH

Both CSRF checks are conditional on their respective headers being present. If a client sends neither Origin nor Sec-Fetch-Site, the entire CSRF guard is silently skipped. Older browsers, some form-submission methods, or adversarial agents could omit both headers.

**Fix:** Reject writes when neither header is present and the request carries an Authorization header.

---

### ATC-005: `_save` in config.py lacks secure-creation pattern

**Source:** Security review
**File:** `src/charon/config.py:170-177`
**Severity:** HIGH

Unlike `secrets.set_secret` (which uses `os.open` with `O_NOFOLLOW`, `0o600`, and atomic `os.replace`), `_save` uses `tmp.write_text()` creating files with default umask (typically 0o644) and no symlink guard. Config dir is not `chmod 0700`.

**Fix:** Use the same secure-creation pattern as `secrets.py`.

---

## MEDIUM

### ATC-006: `_SENSITIVE_ENV` blocklist incomplete
**File:** `src/charon/secrets.py:21-26`

Missing: `PYTHONHOME`, `PYTHONCASEOK`, `PERL5OPT`, `RUBYOPT`, `JAVA_TOOL_OPTIONS`, `GIT_CONFIG_PARAMETERS`, `SSL_CERT_FILE`, `SSL_CERT_DIR`. Defense-in-depth gap.

### ATC-007: `.gitleaks.toml` allowlist regex too broad
**File:** `.gitleaks.toml:14`

`Authorization:\s*Bearer\s*\$\{?[A-Z_][A-Z0-9_]*\}?` matches ANY uppercase env-var reference. A pasted real token starting with `$` character would be allowlisted.

### ATC-008: `DEFAULT_TIER = "sonnet"` — vendor-branded default
**File:** `src/charon/intake.py:62`

Hardcoded Anthropic-specific legacy tier name. Resolves to `"med"` via aliases but the literal is vendor-branded in public source.

### ATC-009: `_is_anthropic()` — vendor-specific CLI logic
**File:** `src/charon/cli.py:730-744`

The `tier resolve --executor` filter only supports `"anthropic"`. No generic executor mechanism. Vendor coupling in public source.

### ATC-010: Dead production modules — `failover.py` and `routing_proxy.py` unwired
**Source:** Regression review
**File:** `src/charon/failover.py`, `src/charon/routing_proxy.py`

Neither module is imported by production code (only tests). `failover.py` defines `ReviewerCircuitBreaker` — exists but no production path reaches it. Either wire or document as not-yet-integrated.

---

## LOW

| ID | File | Finding |
|---|---|---|
| ATC-011 | `proxy_server.py` | Token in URL query persists in browser history even after cookie is set |
| ATC-012 | `proxy_server.py` | Cookie stores raw token value, not derived session token |
| ATC-013 | `recommend.py:137-142` | Model-name heuristic patterns will rot as models evolve |
| ATC-014 | `connect.py` / `cli.py` | `_META_KEYS` inconsistency between CLI and web setup import paths |
| ATC-015 | `gateway.py:29` | `from .cli import _invocation_name` — gateway now imports cli.py engine chain |
| ATC-016 | `cli.py:30-38` | `_invocation_name()` edge case with `python3 -c` returns `-c` |
| ATC-017 | `cli.py:1228` | Default L1 autonomy skips reviewer (by-design, but no cross-model sanity check) |

---

## INFO (cosmetic, no action needed)

| ID | File | Finding |
|---|---|---|
| ATC-018 | `service/app.py:5`, `cli.py:665-668` | Project-internal references in docstrings (fleet, SLOP, droid) — cosmetic only |
| ATC-019 | `recommend.py`, `recommend.py` | `importlib` removed — already fixed in this session |

---

## Clean surfaces (verified, no findings)

| Surface | Verdict |
|---|---|
| `charon run` integrity | No regressions — sandbox/fence policies intact |
| Gateway hot path | No new middleware/parsing; `/v1/models` correct; streaming intact |
| Fresh install flow | Working; new features additive |
| `--open-pr` safety | No auto-merge exists; PRs draft-only |
| Failover chain | Cooldowns expire; cooled providers always in chain |
| Observability isolation | Progress→stderr, JSON→stdout |
| WCI isolation | Dead code — not wired; cannot block work |
| Constant-time token comparison | `hmac.compare_digest` used everywhere |
| Hardcoded secrets in source | None found — test fixtures use fake tokens |
| `scrubbed_env` coverage | Blocks LD_PRELOAD, PYTHONPATH, credentials |
| Stdlib-only core | Zero runtime dependencies; all imports stdlib |
| Provider preset neutrality | Users can override every preset; no provider branching in hot path |

---

## Fix tickets needed

| Ticket | Severity | Scope |
|---|---|---|
| ATC-FIX-001 | CRITICAL | Fix `_load_plan` body drop + `Board.Unit` body param |
| ATC-FIX-002 | CRITICAL | Mask token in gateway startup output |
| ATC-FIX-003 | CRITICAL | Mask token in `charon connect` output |
| ATC-FIX-004 | HIGH | CSRF hardening — reject when neither origin header present |
| ATC-FIX-005 | HIGH | Secure `_save` with O_NOFOLLOW + 0o600 |
| ATC-FIX-006-010 | MEDIUM | Blocklist, gitleaks, tier defaults, anthropic filter, dead modules |
| ATC-FIX-011-017 | LOW | Cookie UX, model heuristics, META_KEYS, import chain, invocation edge case |
