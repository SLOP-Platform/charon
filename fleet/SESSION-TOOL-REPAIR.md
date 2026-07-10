# DeepSeek build session — TOOL-REPAIR: schema-only tool-call repair module (defer the wiring)

You are a Charon build session (DeepSeek V4 Pro). Repo: `/home/stack/code/charon`. Branch off `master`.
Implement the **standalone `src/charon/tool_repair.py` module + its tests + a clean public API ONLY**.
**Do NOT wire it into `proxy_server.py`** — that response-path hook is explicitly DEFERRED to a follow-up
ticket so this session never touches the proxy hot path.

**This session runs in PARALLEL with the RFL-1 and SR-12 sessions — that is SAFE:** all three touch
disjoint files (this one: `tool_repair.py` only), none of them edits `src/charon/proxy_server.py`.

## 1. Ground yourself first (read these)
- `/home/stack/code/charon/AGENTS.md` — standing orders (mandatory).
- `src/charon/response_normalizer.py` — the REFERENCE and **the module you are symmetric to**. That module
  operates on `choices[0].message.content` **strings**; yours operates on
  `choices[].message.tool_calls[].function.arguments`. Match its shape exactly: stdlib-only, deterministic,
  self-contained, a public class + small ordered private helper rules, `from __future__ import annotations`.

## 2. The idea — validate-then-repair tool calls (schema-only)
Open/cheap models (DeepSeek V4, Kimi, etc.) fail on tool-call **formatting/schema adherence** far more than
on intent. Charon has **no tool-call repair layer** today (`response_normalizer` only touches content
strings). This module deterministically repairs the *format/schema* of malformed
`function.arguments` so a weak-but-cheap provider's tool call becomes valid — making the cheap primaries
reliable enough to keep at the top of the draw-down order.

**Ignore the vendor hype.** The source thread claims "16,000 repair variations" — that is marketing
(permutation counting), NOT hand-written rules. At Charon scale this is **a couple dozen ordered rules**,
each one small and testable. Do not try to enumerate thousands of cases.

## 3. Scope — the `tool_repair.py` module ONLY
- branch: `feat/tool-repair` (off latest `master`).
- **owns:** `src/charon/tool_repair.py` (NEW), `tests/test_tool_repair.py` (NEW). Touch NOTHING else.
- **DO build** `src/charon/tool_repair.py` — a stdlib-only (`json`, `re`, `enum`) validate-then-repair
  engine operating on a single tool call's `arguments` string against the tool's declared JSON-schema
  `parameters` (the schema is already present in the request body — no network, stays stdlib-only):
  - **Clean public API** (the seam the deferred proxy wiring will call):
    - `repair_arguments(arguments: str, schema: dict | None) -> RepairResult` where `RepairResult` carries
      the repaired string (or the original if untouched/unrepairable), a `changed: bool`, and the list of
      rule names that fired. Design it so a caller can pass a whole tool_call and get back a repaired one,
      but keep the CORE function operating on the `arguments` string + schema (that is the testable unit).
    - A convenience `repair_tool_calls(tool_calls: list[dict], schemas: dict) -> ...` wrapper is fine if it
      stays thin, but the string-level `repair_arguments` is the primary API.
  - **Ordered, table-driven rule set** — a couple dozen rules max, each a small function keyed by failure
    signature, applied in order (mirror how `response_normalizer` composes its private `_fix_*` helpers).
    Cover the common open-model failures:
    1. **Trailing commas** before `}`/`]` → removed.
    2. **Single-quoted** strings/keys → double-quoted (reuse the same idea as the normalizer's
       `_fix_single_quoted_keys`).
    3. **Unquoted object keys** → quoted.
    4. **Stringified-JSON**: `arguments` is a JSON *string* wrapping the real object/array → unwrap one level.
       Symmetric: an individual property whose schema type is `object`/`array` but whose value is a JSON
       string → parse it.
    5. **Primitive type coercion GUIDED BY THE SCHEMA ONLY**: `"true"`/`"false"` → bool when the schema says
       `boolean`; numeric strings → number when schema says `integer`/`number`. Never coerce when the schema
       is absent or doesn't specify the type.
  - **Validate-then-repair discipline:** first try `json.loads(arguments)` — if it already parses AND (when a
    schema is given) conforms on the shallow structural checks you implement, return unchanged
    (`changed=False`). Only apply repair rules when parsing/validation fails. Do a **light, stdlib
    structural validation** (required keys present, top-level type matches, property primitive types) — do
    NOT pull in `jsonschema` or any third-party validator.
  - **HARD SAFETY RULE — schema/format only, NEVER semantic values.** Repair only *shape/format/type*. Never
    invent, guess, or substitute a value's *meaning* (don't fill a missing required argument with a guessed
    value, don't change `"delete"` to `"list"`, etc.). If a call can't be made valid by pure format/type
    repair, leave it unchanged and report it unrepaired.
  - **OFF by default for state-mutating calls.** Provide a config-gated switch and treat state-mutating tool
    calls conservatively: default behavior must NOT repair a call flagged/detected as state-mutating unless
    explicitly enabled. Since you don't wire the proxy here, expose this as a parameter/flag on the public
    API (e.g. `allow_mutating: bool = False`) and document that the deferred wiring passes it from config —
    do NOT try to infer mutation semantics cleverly; a simple caller-supplied flag is correct.
  - **Per-rule observability counter:** keep an internal counter dict keyed by rule name (which rule fired,
    how often), incremented as rules apply, with a read-only accessor (e.g. `counters() -> dict[str, int]`).
    That telemetry is itself valuable for routing. Keep it self-contained like `response_normalizer.py`.
  - Leave a one-line comment noting the rule table can later be scoped per-`(model, provider)` — but do NOT
    build per-provider scoping now.
- **DO NOT** import or edit `src/charon/proxy_server.py`, `response_normalizer.py`, `config.py`, or anything
  else. If you believe you need a change outside `tool_repair.py` + its test, **STOP and flag it** — do not
  create/edit it. The proxy response-path hook (after the normalizer) is a SEPARATE follow-up ticket.
- **Stdlib-only:** `json`, `re`, `enum`, `dataclasses` — no third-party imports (NO `jsonschema`). No
  fleet/SLOP/runner/`/home/stack`/personal strings anywhere in `src/`.

## 4. Tests — `tests/test_tool_repair.py` (hermetic, no network)
- Already-valid arguments with a matching schema → returned unchanged, `changed=False`, no rules fired.
- Trailing comma / single quotes / unquoted keys each get repaired to valid JSON (one focused test each,
  asserting the fired rule name).
- Stringified-JSON: `arguments = '"{\\"a\\": 1}"'` (a JSON string wrapping an object) → unwrapped to `{"a": 1}`.
- Schema-guided coercion: schema `{"properties": {"n": {"type": "integer"}}}` with `{"n": "5"}` → `{"n": 5}`;
  boolean `"true"` → `true`. And the negative: with NO schema (or type unspecified), `"5"` stays a string.
- **Safety:** a missing required argument is NOT fabricated (returned unrepaired, reported); a semantic value
  is never altered.
- **State-mutating default OFF:** with `allow_mutating=False` (default), a call marked state-mutating is not
  repaired; with `allow_mutating=True` it is.
- `counters()` reflects which rules fired.
- Assert the module imports stdlib-only (no third-party module — especially no `jsonschema`).

## 5. Rules — non-negotiable
- **Gate before commit** — BOTH must be green:
  ```
  python3 -m charon.cli gate && PYTHONPATH=src python3 -m pytest -q
  ```
  `python3 -m charon.cli gate` runs ruff/mypy/boundary/version/gate-registry; pytest is the separate test
  pass. Do NOT use a bare `mypy src/charon` — it misses the test files and reddens CI.
- Commit with a conventional message (e.g. `feat(tool-repair): schema-only tool-call repair module (module + tests)`).
- **Commit your work but DO NOT push and DO NOT open a PR.** Stop after committing — a Claude reviewer + the
  operator gate every merge.

When committed, report the branch name + final `pytest` counts, then stop.

## Dependencies & Sequence
NEW standalone file (`src/charon/tool_repair.py` + `tests/test_tool_repair.py`), **disjoint from
`proxy_server.py`** (the response-path wiring hook is explicitly deferred to a follow-up ticket, so this
session never touches it). **Parallel-safe** with SESSION-RFL-1 (new `quota.py`) and SESSION-SR-12 (edits
`providers.py`/its test) — no shared files, run all three concurrently.
