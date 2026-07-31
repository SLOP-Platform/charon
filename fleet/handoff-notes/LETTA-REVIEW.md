# LETTA REVIEW — deepseek-v4-pro
## VERDICT: REJECT Letta; REJECT mnemostroma (broken); ADOPT-PARTIAL basic-memory scheduling

## FULL CAPABILITY INVENTORY — not pre-filtered by "recall vs follow-through"

### Letta Code v0.29.12
Installed `@letta-ai/letta-code` via npm. Ran headless. Configured provider to
our gateway (required ollama provider workaround — see fit issues). Hit gateway
spend limit so could not complete full LLM turn, but the harness stored my test
message to disk (`~/.letta/lc-local-backend/conversations/*/messages.jsonl`).

**What it actually does (from system prompt, agent config, and runtime):**
1. **Automatic recall memory** — ALL messages from ALL conversations stored in
   jsonl automatically. Agent never writes recall; harness captures everything.
2. **Editable memory blocks (learning memory)** — Agent rewrites its own system
   prompt via git-backed MemFS. Every edit has a commit author and message.
3. **Background reflection agents** — Between-turn agents that consolidate,
   deduplicate, and restructure memory. Comparable to human sleep consolidation.
4. **Scheduling / crons** — Agent creates one-shot or recurring future
   invocations of itself: `letta cron add --prompt "..." --at "in 30m"`.
   Cloud schedules survive local shutdown.
5. **Subagents** — Spawn specialized subagents (fork, recall-search, etc.)
   with own context windows.
6. **Skills** — Procedural memory loaded on demand; reusable across environments.
7. **Mods** — Trusted local code extending the harness (tools, slash commands,
   providers, permission overlays, UI).
8. **Cross-conversation memory** — All conversations for one agent are linked
   and searchable via recall subagent.
9. **Git-backed memory versioning** — Full commit history. Can revert.
10. **Memory compaction** — Older messages summarized as context fills.
11. **`/remember`, `/doctor`, `/init`, `/search`** — Structured memory management.
12. **MemFS filesystem** — Memory projected to `$MEMORY_DIR` for grep/bash.
13. **Persistent agent identity** — Agent ID travels across environments.
14. **Provider-agnostic** — OpenAI, Anthropic, Ollama, openai-compatible, Gemini.
15. **Permission system + hooks** — allow/deny/ask rules, lifecycle hooks.

### mnemostroma v2.5.2 (broken)
Cloned repo (226 commits, 165 source files, ~24.6K LOC Python). Installed via
`pip install -e "[all]"`. Daemon started but storage init crashed on missing
`mnemostroma.gateway.outbox`. The MCP tool listing DID succeed via stdio,
revealing 11 tools.

**What the code + tools claim to provide:**
1. **Observer pipeline** — Automatic extraction from conversation streams.
   Agent NEVER calls "save_memory"; Observer handles everything silently.
2. **Dreamer** — Background distillation and memory consolidation.
3. **5 memory layers**: Ledger (exact facts: dates, URLs, names), Experience
   (fading context), Subconscious (eternal embeddings), Anchor (decisions,
   deadlines), Precision (links, quotes).
4. **Memory decay / Dissolver** — Old fades; frequently accessed stays;
   principles never dissolve. Fixed 600MB budget.
5. **Anchor system** — Decisions, facts, people, events, deadlines extracted
   and indexed SEPARATELY from narrative memory.
6. **Precision layer** — Links, formulas, quotes stored with versioning.
7. **Context bridge** (`ctx_bridge`) — Structured handoff packet for next agent.
8. **Content branch** — Code/docs/configs versioned with diffs and `why_changed`.
9. **Semantic search** — MatrixSearch ANN on ONNX embeddings (~20ms).
10. **Gateway** — Passthrough proxy that captures LLM completions into memory.
11. **Browser extension** — Captures Claude.ai, ChatGPT, Gemini web chats.
12. **Cloudflare Tunnel + OAuth** — Remote MCP from web chat interfaces.
13. **NER entity extraction** — distilbert-ner model, runs on all observed text.
14. **Contradiction detection** — Keyword + async anchor conflict checking.
15. **Continuation detection** — Recognizes when new session continues a prior one.

**Why it is broken and unrunable:**
The "sync from Repo A" (commit 403537f, 2026-07-29) introduced imports for files
that only exist in a private repo:
- `RawObservation` class: imported by `sqlite.py:11` and `conductor.py:683`,
  but never defined in the public repo (stub required to even import)
- `mnemostroma.gateway.outbox`: imported by `sqlite.py:74` and `server.py:19`,
  file does not exist
- `mnemostroma.gateway.observer_bridge`: imported by `server.py:18`, file DNE
- `mnemostroma.gateway.upstream_router`: imported by `server.py:20`, file DNE
- `mnemostroma.gateway.openai_facade`: lazy import in `server.py:195`, file DNE

The MCP tools listing succeeds (it doesn't import storage modules), but the
daemon cannot start fully. 11 tools register, 0 functional end-to-end queries.

### Basic-memory (already adopted — for comparison)
Already deployed as MCP server. Retrieves memories semantically. Requires
explicit write calls. No scheduling, no background processing, no automatic
extraction, no contradiction detection, no memory decay, no session bridge.
Finished: FN1-MEMORY-STORE-ADOPT, MEMORY-WIRE-RETRIEVAL. Not finished:
MEMORY-INDEX-COMPACTION, MEMORY-RETIRE-ADOPT (curation wrappers, landed today).

## CAPABILITIES WITH NO ANALOGUE IN BASIC-MEMORY

| Capability | Letta | mnemostroma | What it would let us do |
|---|---|---|---|
| Scheduling future invocations | YES (crons) | No | Agent at T0 creates a self-nudge at T+30m; follow-up is structural, not dependent on recall |
| Automatic extraction (no write call) | YES (recall) | YES (Observer) | The "things never got written down" gap closes because the harness writes without being asked |
| Background memory consolidation | YES (reflection) | YES (Dreamer) | Memory improves during idle between sessions without consuming agent turns |
| Session bridge / handoff packet | No (but crons simulate it) | YES (ctx_bridge) | Every session gets a non-optional structured context summary from the last session |
| Contradiction / conflict detection | No | YES (Anchor Guardian) | If new session says "done" but anchors say "deferred", the contradiction is flagged before action |
| Memory decay | No | YES (Dissolver) | Prevents indefinite growth; unused facts fade, principles persist indefinitely |
| Git-backed memory versioning | YES (MemFS) | No | MemFS provides audit trail of memory edits with author attribution, which is a primitive form of accountability |
| Owns the agent loop | YES (framework) | No (sidecar daemon) | Letta is the agent driver — replaces opencode. mnemostroma sits alongside — complements opencode |

## MAPPING TO MEASURED FAILURES

**Failure 1: 26 branches with unlanded commits, 16 ≥7 days**
- Scheduling (Letta): if the agent that created work also scheduled a self-check,
  a cron would fire and ask "is branch X landed yet?"
- Auto-extraction (mnemostroma): if the Observer captured "created branch for
  MEMORY-INDEX-COMPACTION" automatically, the fact wouldn't vanish
- Session bridge (mnemostroma): next session gets "BRANCH xyz: unlanded" in
  its context bridge packet

**Failure 2: 43 parked tickets, 17 stale claims, 16 open PRs**
- Scheduling: interval cron reviewing open tickets would surface parked items
- Contradiction detection: "I claimed this ticket" vs. "this ticket hasn't been
  updated in 7 days" — anchor guardian could flag the staleness

**Failure 3: LiteLLM: 1063 LOC, 4/5 tickets DONE, but live gateway does not import it**
- Auto-extraction: the Observer would capture the decision "LiteLLM is adopted
  as a library (ADR-0017)" automatically, so next sessions know the status
- Scheduling: a cron set at ADOPT-DECISION time to follow up on integration
  completion would have fired before the week-long silence

**Failure 4: ADOPT-MAP.md:65 says "DEFERRED, NOT silently dropped" — then silent for a week**
- Contradiction detection (mnemostroma): "we deferred this" (anchor) vs. "we
  haven't mentioned this topic in 7 days" (temporal staleness) = flagged
- Scheduling: "deferred to next slice" — should have created a cron with that text
- Session bridge: next session's handoff packet would include the deferral note

**Failure 5: 60+ persistent memories loaded, none prevented any of the above**
- Current basic-memory memories are UNDIFFERENTIATED — all are just text blobs
  retrieved by semantic similarity. No special handling for commitments vs.
  preferences vs. facts.
- mnemostroma's anchor/precision/experience split would differentiate them.
  "MEMORY-INDEX-COMPACTION due Friday" would be an anchor (deadline), not just
  another memory entry.
- Neither tool fixes the ROOT CAUSE: nothing in the system BLOCKS on an
  unfinished commitment. Both improve detection but don't enforce.

## FIT ASSESSMENT

### Letta
- **Control direction**: FRAMEWORK, not library. Letta OWNS the agent loop.
  Our rig runs opencode as the agent driver. Adopting Letta means REPLACING
  opencode, not complementing it. **Fit-without-bending failure.**
- **Coexistence with basic-memory**: No. Letta is a competing agent harness.
  You run EITHER Letta OR opencode+basic-memory, not both.
- **Exit cost after 6 months**: HIGH. Agents, skills, mods, conversations,
  memory blocks all in Letta's proprietary MemFS format. No export path.
- **Maintenance liveness**: ACTIVE. 24K stars, frequent releases, active Discord.
- **Cloud-gated**: Provider setup validates against api.letta.com. I worked
  around this by using the "ollama" provider type pointed at our gateway, then
  manually patching to "openai" in auth.json. This path is undocumented and
  fragile.
- **Provider-agnostic claim**: Partially true. The harness supports many
  providers, but provider SETUP gates through Letta Cloud.

### mnemostroma
- **Control direction**: SIDECAR DAEMON. Runs alongside the agent. Agent calls
  MCP tools for reads; daemon does writes automatically. **Good fit.**
- **Coexistence with basic-memory**: YES. It's an MCP server — could run alongside
  basic-memory. Overlapping capability (both provide semantic retrieval), but
  mnemostroma adds auto-extraction, anchors, contradictions, decay.
- **Exit cost after 6 months**: LOW-MEDIUM. Data in SQLite WAL + ONNX models.
  Standard formats. Could extract memories as JSON.
- **Maintenance liveness**: CONCERNING. Single developer (GG-QandV). 226 commits
  but some are partial merges from a private repo that introduce broken imports.
  The bus factor is 1.
- **Broken public release**: v2.5.2/3 cannot start the daemon without fixing
  missing modules. This is a packaging problem from the "repo A sync". Either
  the developer will fix it (active) or it's maintainer-blind.

## VS FINISHING basic-memory (MEMORY-INDEX-COMPACTION)

Basic-memory is half-built and already running. The remaining work is
MEMORY-INDEX-COMPACTION (deduplication + index compaction for retrieval
performance). Adding scheduling on top of basic-memory (a "memory cron"
that injects relevant stored commitments into the system prompt at session
start) would buy more than either Letta or mnemostroma:

1. **It addresses the root cause**: The problem is not that memories don't
   exist — 60+ are loaded. It's that nothing BLOCKS on them. A scheduling
   layer that INJECTS active commitments into the context window at session
   start would directly address this.
2. **It stays within the adopted architecture**: basic-memory is already wired.
   Adding a scheduling/injection layer is additive, not replacement.
3. **No inversion of control**: The rig stays provider- and agent-agnostic.
4. **Lower risk**: No dependency on an external project with unknown maintenance.

The scheduling capability from Letta (crons) is the single most relevant
idea. We don't need Letta-the-harness to get it — a small layer that reads
stored commitments and injects them into each session's system prompt would
achieve the same effect with basic-memory as the store.

## mnemostroma

### From the CODE (not the pitch)
- 165 Python source files, ~24.6K LOC, 103 test files (1556 passing claimed)
- Architecture: asynchronous dual-stream pipeline (Observer + Content) over
  ONNX embeddings + SQLite WAL
- Formal hexagonal architecture with Port/Repository adapter interfaces
- ONNX models (~300MB): multilingual-e5-small (384d embeddings), distilbert-ner
  (entity extraction), TinyBERT (reranking)
- No torch, no transformers, no LangChain, no Docker, no cloud
- 11 MCP tools: ctx_semantic, ctx_get, ctx_search, ctx_full, ctx_anchors,
  ctx_precision, content_search, content_raw, content_history, ctx_bridge,
  ctx_recent
- FSL-1.1-MIT license (acceptable)

### How I ran it
```sh
git clone https://github.com/GG-QandV/mnemostroma.git /tmp/mnemostroma-full
python3 -m venv /tmp/mnemostroma-venv
/tmp/mnemostroma-venv/bin/pip install -e "/tmp/mnemostroma-full[all]"
# Two import errors patched:
#   1. RawObservation class missing from session_index.py → added stub dataclass
#   2. mnemostroma.gateway.outbox missing → fatal, daemon init crashes here
/tmp/mnemostroma-venv/bin/mnemostroma setup   # OK
/tmp/mnemostroma-venv/bin/mnemostroma on      # starts but storage init crashes
```
**"Could not run it"**: The daemon starts (process visible in ps) but storage
initialization crashes on missing `mnemostroma.gateway.outbox`. The MCP tool
listing via stdio succeeds (`mnemostroma mcp` with `tools/list` returns 11 tools),
but no end-to-end observation→query cycle was possible.

### Verdict on mnemostroma
**REJECT for now — unrunable.** The capability pitch is strong (auto-extraction
without explicit write, anchor/precision split, context bridge), but the current
public release is broken. If the developer fixes the "Repo A sync" issues and the
tool becomes runnable, re-evaluate as WATCH. The architecture (sidecar daemon,
MCP interface) has good fit with our stack.

### vs finishing basic-memory
mnemostroma's auto-extraction and context bridge have no analogue in basic-memory
today. But basic-memory is RUNNING and mnemostroma is NOT. Finishing
MEMORY-INDEX-COMPACTION and adding a scheduling/injection layer above
basic-memory is lower risk and immediately actionable.

## Mem0 / Memory Bank / non-memory alternatives — brief

- **Mem0**: Claims automatic memory extraction without explicit write call.
  Cloud-dependent. The "no explicit write" property is the single most relevant
  capability in this evaluation — Mem0 should be run and tested if time permits.
  Not evaluated here (brief scope is Letta).
- **Memory Bank markdown**: Purely a convention — files the agent reads at
  session start. Requires DISCIPLINE to maintain. Our failure mode is lack of
  discipline (ADOPT-MAP.md had the info and was ignored). More markdown files
  does not solve the core problem.
- **Non-memory alternative — scheduling/injection layer**: The strongest
  non-memory answer. A small component that (a) maintains a registry of active
  commitments, (b) injects them into the session prompt at startup, (c) flags
  staleness. Built on basic-memory as the store. This addresses follow-through
  structurally rather than relying on the agent remembering to search.

## ADOPT-CANDIDATES: NONE

What I tried hardest to make work:
1. Installed Letta Code v0.29.12, configured a provider to our gateway
   (required undocumented ollama→openai provider type swap). Message
   persistence confirmed but no full LLM turn due to gateway spend limits.
   Regardless, the fundamental fit issue (Letta OWNS the agent loop — conflicts
   with opencode) makes it a non-starter for our architecture.
2. Installed mnemostroma v2.5.2 from git, patched two missing imports. The
   daemon starts but storage init crashes on missing `gateway.outbox` module.
   The 11 MCP tools register but 0 functional queries completed.
3. The most promising capability — auto-extraction without explicit write —
   is present in both tools but neither was runnable end-to-end today.
   **If one must be run again**: mnemostroma after the developer fixes the
   Repo A sync issue, because its sidecar architecture coexists with opencode.
   Letta's agent-harness architecture does not.

## RECOMMENDATION

1. **Do not adopt Letta.** It's an agent harness competing with opencode, not a
   tool complementing it. The scheduling/crons capability is the single idea
   worth extracting.
2. **Do not adopt mnemostroma** until the public repo is runnable. Watch it.
3. **Build a commitment-injection layer above basic-memory.** At session start,
   read stored commitments from basic-memory, inject them as non-optional
   `<system-reminder>` blocks. Flag staleness. This addresses the actual failure
   (nothing blocks on unfinished commitments) without replacing the adopted
   memory store.
4. **Investigate Mem0** for the "auto-extraction without explicit write"
   capability, if mnemostroma remains broken.
