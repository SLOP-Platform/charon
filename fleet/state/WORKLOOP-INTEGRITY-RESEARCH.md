# Work-loop-integrity — adopt-first research (2026-07-22, deep-research: 23 sources, 25 claims 3-vote-verified)

Solution-seeking search for adoptable tools to close Charon's work-loop seams (built-but-not-wired,
stale board, gates that silently don't run). **Answer = a layered adopt-first STACK, wrap-not-rewrite.**
The three novel picks were VERIFIED REAL via GitHub API 2026-07-22 (not hallucinated).

## The stack (by seam)
| Seam / need | Adopt | Verified | Notes / caveats |
|---|---|---|---|
| Feedback-loop glue (CI/review/merge → back to originating agent) | **agent-orchestrator ("ao")** `AgentWrapper/agent-orchestrator` | 8.5k★ Go, pushed 2026-07-22 | Routes CI fails/review/conflicts back to the agent until PR approved. Does NOT enforce a DoD |
| Meta-orchestration + policy gates, gateway-native | **Omnigent** `omnigent-ai/omnigent` | 7.6k★ Py, pushed 2026-07-23 | Any OpenAI/Anthropic base_url (Ollama/vLLM/LiteLLM); approval gates, spend caps, tool-call limits. ⚠️ alpha; "Databricks" attribution UNCONFIRMED |
| Durable stage automation (glue-as-code) | **Windmill** (NOT n8n) | established | Checkpoint/resume, git-synced workflows-as-code. Temporal if max durability > ops burden |
| State-truth / anti-drift (auto-retire, catch unwired) | **reconciliation-loop PATTERN** (K8s desired-vs-actual; GITER arXiv 2511.04182) | pattern | IMPLEMENT not install — this IS the board-trust/auto-retire fix |
| Enforced DoD | **merge queue + trunk-based two-gate**; **Archon** `coleam00/Archon` as reference harness | Archon 23k★ TS | Machine CI + human review before trunk. ⚠️ merge queue needs a PAID plan for the private rig; public product repo gets it free |
| Whole-replacement fallback | **OpenHands** | established | LiteLLM/any-model/self-host, if we ever retire the per-agent harness |

## n8n verdict: NEGATIVE for reliable glue
No automatic checkpoint/resume; under a crash it marks workflows "crashed" + needs manual restart —
literally reintroduces our "gate silently didn't run" failure class. Adopt **Windmill** instead.
Durability ranking: Temporal > Windmill > n8n.

## Open questions (the spike must answer, hands-on)
1. **ao**: works with Gitea-primary + GitHub-mirror, or GitHub-API-coupled? (make-or-break)
2. **Omnigent**: actually drives our local gateway with non-Claude models? alpha-maturity real risk?
3. **Windmill**: solo-operator ops burden (Postgres + workers) day-to-day; DoD-stages-as-git-flows viable?
4. **Archon**: composes on top of ao, or conflicts on worktree/merge ownership?

## Rejected (with reasons — pattern-donors only)
- **Vibe Harness** (myshkin451) — markdown doc-scaffold; explicitly rejects enforced git/PR/DoD ("map not manual, runway not a cage"). Context scaffold only.
- **Overstory** (jayminwest) — archived read-only 2026-05-28, Claude-Code-first, superseded by "Warren". Pattern-donor (worktree + SQLite FIFO merge queue + role guards); evaluate Warren if adopting from this lineage.

## Discovery substrate (for future shortlisting, avoid blind re-search)
`RyanAlberts/best-of-Agent-Harnesses` (135+, rescored weekly), `ai-boost/awesome-harness-engineering` (CC0).

## Caveats
Fast-moving space (all sources Jun–Jul 2026). Omnigent alpha. Durability ranking leaned partly on one
blog (arcbjorn, HTTP 403 at verify) but corroborated by official docs + a GitHub issue. GITER is a
design white-paper (pattern, not a product). Re-verify maturity before committing.
Full run: deep-research wf_7fc6aeee-0cf (this session).
