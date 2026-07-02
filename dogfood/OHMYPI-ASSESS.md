# OHMYPI-ASSESS — oh-my-pi as a Charon client

**Date:** 2026-06-29  
**Type:** research pass  
**Source:** GitHub repo + README analysis + existing `charon connect omp` implementation

## 1. What oh-my-pi is

oh-my-pi (npm: `@oh-my-pi/pi-coding-agent`, binary: `omp`) is a coding agent framework
forked from [Pi](https://github.com/badlogic/pi-mono) by @mariozechner. It is:

- **Terminal-first** with a TUI, plus one-shot (`omp -p`), RPC, and ACP modes
- **Rust + TypeScript** — ~55k lines of Rust for in-process search, shell, AST, LSP, debugger
- **Multi-provider** — 40+ providers, custom OpenAI-compatible entries in `~/.omp/agent/models.yml`
- **Extensible** — plugins, slash commands, tool extensions
- **MIT licensed**, stars: ~15k

Key characteristics relevant to Charon:
- **Mode A (gateway client):** oh-my-pi supports custom OpenAI-compatible providers via
  `~/.omp/agent/models.yml`. This is exactly the config file that `charon connect omp` (#72)
  already writes. The wire-up is: Charon gateway → omp points at it as a custom provider.
- **Mode B (ACP backend):** oh-my-pi supports ACP (`omp acp`), the same protocol that
  Charon's `AgentBackend` uses. It could theoretically be driven as a Charon worker, though
  Charon currently hardcodes `opencode` as its ACP binary.

## 2. Does `charon connect omp` work as-is?

**Yes.** The existing implementation (#72) writes:

```yaml
# ~/.omp/agent/models.yml
charon:
  provider: openai-compatible
  base_url: <gateway-url>/v1
  api_key: <CHARON_GATEWAY_TOKEN>
  model: <discovered-model-id>
```

This matches oh-my-pi's documented custom provider schema. The model discovery against
the gateway's `/v1/models` endpoint produces a valid model id. Idempotent re-runs preserve
the user's other config keys.

### Confirmed gaps

**Windows/PATH gap:** On Windows, `omp` installed via npm/bun globals may not be on PATH
when `charon connect omp` runs. The existing `_install_omp` already handles this
(connect.py:328-338) — it detects the OS and returns the correct install command, but the
verify step (`shutil.which("omp")`) may fail on Windows even after install. This is a
pre-existing UX issue documented in connect.py's "omp/Windows PATH gap" comment
(connect.py:355).

**No other gaps identified.** The config schema is stable and matches.

## 3. Could oh-my-pi drive `charon work` as an ACP backend (Mode B)?

Potentially, but not today. Charon hardcodes `opencode` as its ACP binary in
`adapters/acp.py`. Supporting `omp acp` would require:

1. Abstracting the ACP binary selection in the agent launch path
2. Confirming `omp acp` speaks the ACP protocol version Charon expects
3. Testing end-to-end

This is not a small change — it would be a new integration ticket. oh-my-pi's ACP
documentation confirms it supports the protocol and runs inside editors (Zed), so
the technical possibility exists.

## 4. Recommendation

**Nothing immediate.** `charon connect omp` already wires oh-my-pi as a gateway client
(Mode A) correctly. The Windows PATH gap is a pre-existing issue tracked in the code.

**Future consideration:** If an operator needs oh-my-pi as a Charon worker (Mode B/ACP),
open a fresh ticket to:
1. Abstract ACP binary selection in `adapters/acp.py` / `agent_launch.py`
2. Verify `omp acp` protocol compatibility
3. Add `omp` as a configurable ACP backend option

This is NOT a blocker and NOT a dependency for any current build ticket.
