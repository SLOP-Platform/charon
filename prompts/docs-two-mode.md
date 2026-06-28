Implement the OPERATOR-APPROVED two-mode onboarding for Charon: make a newcomer instantly
see that Charon is TWO things (a smart LLM gateway, and an opt-in autonomous coding
orchestrator), pick the mode they want, and get a working quickstart for it. This is a
PRODUCTION-READINESS onboarding priority — the current README leads with jargon and never
surfaces the orchestrator until far down the page.

THE CONTENT IS ALREADY APPROVED. Do NOT reinvent the copy or change any commands.
The source of truth is the draft:

  /home/stack/charon-private/dogfood/TWO-MODE-ONBOARDING-DRAFT.md

Reproduce its wording and structure FAITHFULLY: the "Charon in 20 seconds" block, the
"Which mode do I want?" table, the Mode A (Gateway) quickstart, and the Mode B
(Orchestrator) quickstart. You MAY adapt markdown formatting to fit the README/docs, but
you MUST NOT rewrite the prose or alter the commands. Every command in the draft was
verified against the real CLI (`charon setup`, `charon gateway`, `charon intake import`,
`charon work --units … --repo … --backend acp --acp-cmd 'opencode acp'`, `charon ledger`,
`docker compose run --rm gateway setup`, `docker compose up`) — keep them exactly.

READ FIRST (read-only; the local checkout may be stale, so read the repo fresh —
use `git show origin/master:<path>` if needed):
- /home/stack/charon-private/dogfood/TWO-MODE-ONBOARDING-DRAFT.md  (the approved content)
- README.md on origin/master — note its current intro and existing section anchors:
  `## Install`, `## Quick start`, `## Providers & keys`, `## Connect a client`,
  `## Failover`, `## Expose it / Docker`, `## Work engine (opt-in)`, `### Intake …`,
  `## License`. The deep Mode-B vocabulary (fenced coordinator, propose-default land,
  AIMD capacity, positive-isolation, sandbox postures, ADR / `D0xx` refs) lives in the
  `## Work engine (opt-in)` section.
- docs/ on origin/master — convention: lowercase topical files like `docs/docker.md`
  alongside UPPERCASE design docs (`docs/DECISIONS.md`, `docs/PLAN-tierN.md`, `docs/adr/`).
  There is NO docs index file; the README points at docs with inline links such as
  `[docs/docker.md](docs/docker.md)`. Match that pattern.

DELIVER (own ONLY `README.md` and `docs/getting-started.md` — see the ticket):

1. README intro — REPLACE the jargon-heavy single-paragraph intro at the TOP.
   - Keep the `# Charon` H1.
   - REPLACE the current opening pitch — the bold "A local, OpenAI-compatible gateway with
     visible, cost-ranked failover." tagline paragraph PLUS the three bullets under it
     (the "Works with any OpenAI-compatible client", "Holds your provider keys
     server-side", and "Failover is **visible**: `X-Charon-*` headers" bullets) — i.e.
     everything between `# Charon` and the `## Install` heading.
   - PUT IN ITS PLACE the approved landing content from the draft: the "Charon in 20
     seconds" block, the "Which mode do I want?" table, and the Mode A and Mode B
     quickstarts. This is the draft's stated replacement: the old intro only describes
     Mode A (cost-ranked failover / `X-Charon-*` headers) and never surfaces the
     orchestrator — your job is to make the two-mode split the FIRST thing a newcomer sees.
   - LANDING CONTENT MUST STAY JARGON-FREE. Do NOT pull the deep Mode-B internals into the
     intro. Terms like *fenced coordinator*, *propose-default land*, *AIMD capacity*,
     *positive-isolation*, sandbox postures, and ADR / `D0xx` references stay DOWN in the
     existing `## Work engine (opt-in)` section. Do NOT delete or gut that section — it
     keeps its content; you are just no longer LEADING with it.
   - COLLISION / ANCHOR SAFETY: do not break existing README anchors or internal links.
     There is already a `## Quick start` section (`charon setup` / `charon gateway`) and an
     `## Install` section just below your new intro; the new Mode A quickstart overlaps
     them. Keep the new top block TIGHT and skimmable; let the existing `## Install` /
     `## Quick start` / `## Connect a client` sections remain as the deeper reference. If
     light de-duplication helps readability you MAY trim redundant lines, but you MUST
     preserve the existing section HEADINGS/anchors (`## Quick start`, `## Install`, etc.)
     so no existing link breaks. Prefer adding the skimmable intro over restructuring the
     whole page.

2. NEW docs/getting-started.md — carry the SAME approved two-mode content (the 20-seconds
   block, the mode-decision table, and the Mode A + Mode B quickstarts), slightly EXPANDED
   where natural for a standalone getting-started page:
   - the client base-URL / API-key / model table (from the draft's "Point your client at
     it" table — Base URL `http://127.0.0.1:8080/v1`, key = gateway token or any non-empty
     value, model = a served id or a pool name like `auto`),
   - the Docker path (`cp .env.example .env`, `docker compose run --rm gateway setup`,
     `docker compose up`),
   - the verify curl (`curl http://127.0.0.1:8080/v1/models`).
   Keep it product-clean and jargon-free in the landing portion. Cross-link to the deeper
   docs where useful (e.g. `[docs/docker.md](docker.md)` for the full Docker guide) but do
   NOT duplicate those guides wholesale.
   NOTE the filename is PROVISIONAL: `docs/getting-started.md` is the default (matches the
   lowercase `docs/docker.md` convention and reads as the obvious landing doc). If a
   `docs/quickstart.md` name clearly fits the repo better, you MAY use that instead — but
   pick ONE name and use it CONSISTENTLY in the file itself, the README pointer (item 3),
   and your PR description, and FLAG the rename in the PR.

3. README pointer — add ONE short line near the top of the README intro pointing newcomers
   at the getting-started page, matching the repo's inline-link pattern, e.g.
   "New here? Start with [getting started](docs/getting-started.md)." (The draft suggests
   this exact pointer, worded for `docs/two-modes.md`; retarget it to the filename you
   actually create.) Do not add a heavy docs index — a single inline pointer is enough.

CONSTRAINTS (hard):
- PRODUCT-CLEAN: zero SLOP / fleet / build-rig / runner leakage into README or docs.
- AGENT- & PROVIDER-AGNOSTIC: nothing hardcoded to a single agent (opencode is only an
  EXAMPLE ACP backend) or provider; the gateway fronts any OpenAI-compatible provider.
- ACCURATE to the REAL CLI: keep every command exactly as in the draft (all verified).
  Do not invent flags or subcommands.
- Keep the landing content TIGHT and SKIMMABLE; jargon-free.
- Do NOT break existing README anchors/links.
- Own ONLY `README.md` and `docs/getting-started.md` (the docs filename you settle on).
  Do not touch `src/`, `docs/docker.md`, ADRs, or other files. If you believe a code or
  other-file change is required, STOP and flag it instead.
- Base your branch on `master`, open a DRAFT PR, do not merge.
