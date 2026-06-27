## 2026-06-26 — import-all-models (catalog import) — plan note + self-review

Operator-requested (handoff "DO FIRST"). Small, self-contained feature; a plan
note + adversarial self-review here (not a full ADR — no architectural fork).

- **Change under review:** pull a provider's full model list from its
  `/v1/models` (with the stored key) and add them all to config as a **catalog**
  (each becomes selectable + listed at `/v1/models`). Three surfaces:
  `charon models import <provider> [--free-only] [--into-pool <name>]`; a y/N
  prompt in `charon setup` after a provider+key is added; an "import" button +
  `POST /charon/models/import` on the web setup page.
- **Framing (binding):** import populates the **catalog**, not pools. POOLS stay
  curated (small, comparable, cost-ranked). `--into-pool` is an explicit opt-in
  escape hatch and prints a "pools work best small" caveat; the wizard import and
  the web import never touch pools.
- **Design:** `providers.list_models(name, overrides, *, api_key)` does
  `GET <base>/models` (key as Bearer), parses the OpenAI `{data:[{id,...}]}` shape
  via a pure `_parse_models`, and flags free models (`:free` suffix or
  `pricing.{prompt,completion}` all 0). `config.add_models_bulk(entries, provider=)`
  writes the catalog in ONE atomic save, skipping (not raising on) ids that fail
  `_ID_RE`. A shared `cli._import_models` helper backs the CLI command + the
  wizard prompt; `gateway.make_setup_handler` adds a `models/import` action.

- **Adversarial self-review (lens: key-exfil / SSRF / DoS / parse-injection):**
  - **[HIGH] key shipped to a bad host.** `list_models` sends the real key as a
    Bearer. Mitigation: reuse the existing guards — refuse non-http(s) and
    link-local/metadata hosts (mirrors `providers test` / `add_provider`), and
    **disable redirects** (`_NoRedirect`) since urllib does NOT strip
    `Authorization` cross-host. The base was already SSRF-validated at
    `add_provider` time; we re-validate at fetch time (defence in depth).
  - **[MED] response-size DoS.** A hostile/huge `/models` body could OOM. Cap the
    read at 1 MB and raise past it.
  - **[MED] catalog-poisoning via crafted ids.** Upstream ids are untrusted.
    `add_models_bulk` validates every id against `_ID_RE` and silently skips bad
    ones (reported as a count), so a malformed id can never reach a route/path.
  - **[LOW] web import is a slow outbound call on the request thread.** The server
    is `ThreadingMixIn`, so one slow import does not block other requests; the
    20 s timeout bounds it. Network errors are caught and surfaced as a 400 with a
    generic message (no path/secret leak), consistent with the existing handler.
  - **[LOW] catalog id collisions across providers** (two providers both list
    `gpt-4o`) → last-write-wins. Acceptable for a catalog; documented.
  - **Verified-correct (kept):** token gate + CSRF/Origin + Host-rebinding guard
    already wrap `POST /charon/models/import` (same dispatch); the key is never
    echoed back (import returns counts only); `--free-only` filters before write.
