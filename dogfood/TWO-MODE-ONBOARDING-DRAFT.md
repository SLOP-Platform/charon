<!-- DRAFT for operator review. Proposed for: top of README.md + new docs/two-modes.md.
     Every command below was verified against origin/master src/charon/cli.py + README.md. -->

# Charon in 20 seconds

**Charon is two things in one tool:**

1. **A smart LLM endpoint** — a local, OpenAI-compatible API gateway that automatically fails over across your providers. Point any OpenAI client at it and stop babysitting rate limits.
2. **An autonomous coding worker** — point Charon at a repo and a to-do list, and it does the work itself: drives a coding agent through the tasks and opens a pull request for each one.

Most people only need #1.

---

## Which mode do I want?

| You want… | Use | What Charon is here |
|---|---|---|
| A reliable LLM endpoint for your tools (Cursor, Cline, Aider, opencode, your own app) | **Gateway** | Just the smart model backend. It answers model calls; **your** agent does the work. |
| Charon to autonomously do coding work from a list of tickets | **Orchestrator** | The worker itself. It drives a coding agent through your tasks and opens PRs. |

> In **Gateway** mode, Charon never touches your code or your tickets — it only answers API calls.
> In **Orchestrator** mode, Charon *is* the one doing the coding work.

---

## Mode A — Gateway (the default, what ~80% of users want)

Charon runs locally and speaks the OpenAI API. You point any OpenAI-compatible client at it, and Charon picks a provider, holds your keys server-side, and fails over to the next provider automatically when one hits a rate or credit cap — same request, no waiting.

**Quickstart:**

```bash
# 1. Install
pipx install git+https://github.com/SLOP-Platform/charon
#    (or run the bootstrap installer — see Install below)

# 2. Add your providers, keys, and models (guided)
charon setup

# 3. Start the gateway
charon gateway          # serves http://127.0.0.1:8080/v1   (console at http://127.0.0.1:8080/)
```

**Point your client at it:**

| Setting | Value |
|---|---|
| Base URL | `http://127.0.0.1:8080/v1` |
| API key | the gateway token if you set one, else any non-empty value |
| Model | a served id, or a pool name like `auto` for failover |

**Verify it's up:**

```bash
curl http://127.0.0.1:8080/v1/models
```

**Prefer Docker?** No host Python needed:

```bash
cp .env.example .env                       # set CHARON_GATEWAY_TOKEN
docker compose run --rm gateway setup      # one-time provider/model setup
docker compose up                          # gateway on http://127.0.0.1:8080/v1
```

That's it. Your client now has automatic multi-provider failover behind one URL.

---

## Mode B — Orchestrator (opt-in, advanced)

Here Charon does the coding itself. You give it a work-list and a repo; it turns the list into a runnable plan, drives a coding agent through each task in parallel, and **opens a pull request for each one (it never auto-merges — a human merges).**

**Quickstart:**

```bash
# 1. Turn your to-do list (markdown) into a reviewable plan
charon intake import my-tasks.md
#    -> writes my-tasks.md.plan.json and prints it for you to review

# 2. Run the plan against your repo with a real coding agent
charon work --units my-tasks.md.plan.json \
            --repo /path/to/your/repo \
            --backend acp --acp-cmd 'opencode acp'
#    -> drives each task to green tests, opens a PR per task
```

> Without `--backend acp --acp-cmd ...`, `charon work` uses a built-in `mock` worker
> (great for a dry run). Real coding work needs a real ACP agent like `opencode acp`.

Check on a task any time with `charon ledger <task-id>`.

---

## Install (both modes)

One-liner bootstrap (checks Python ≥3.11 / git / pipx, installs what's missing):

```bash
curl -fsSL https://github.com/SLOP-Platform/charon/releases/latest/download/install.sh | bash
```

Already have Python 3.11+ and pipx? `pipx install git+https://github.com/SLOP-Platform/charon`.

---

## Where this goes / what it replaces

- **Top of `README.md`** — replace the current single-paragraph intro (which leads with
  "visible, cost-ranked failover" and `X-Charon-*` headers) with the **"Charon in 20 seconds"**
  block + the **"Which mode do I want?"** table. The current intro only describes Mode A and
  never tells a newcomer the orchestrator exists or that it's optional, so the two-mode split
  is invisible until the "Work engine (opt-in)" section far down the page.
- **New `docs/two-modes.md`** — the full version above, linked from the README intro
  ("New here? Start with [the two modes](docs/two-modes.md)").
- **Cut/soften from the README intro for newcomers:** the deep Mode-B jargon should stay in
  the existing "Work engine" section, not the landing pitch — terms like *fenced coordinator*,
  *propose-default land*, *AIMD capacity*, *positive-isolation*, sandbox postures, and ADR/`D0xx`
  decision references. A new user should hit the two-mode split first and only meet that
  vocabulary once they've chosen Orchestrator.
