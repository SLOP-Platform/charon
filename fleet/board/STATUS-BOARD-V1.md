repo: charon-private
tier: economy
priority: 2
difficulty: 3
work_class: ci-infra
branch: feat/status-board-v2
owns: fleet/status-board/generate.sh, fleet/status-board/board.html, fleet/tests/status-board.test.sh
depends_on:
dep-kind:
serial_justified: |
  PRE-EXISTING gate-parity RED, fixed 2026-08-04 rather than stepped over. The
  owned surfaces are a generator, the artifact it emits, and its red-proof — one unit. The HTML is
  OUTPUT of the generator, not an independent surface, so there is nothing to parallelise; a split
  would hand one agent a page it cannot regenerate and another a generator with nothing to verify.
work_class_note: ci-infra — the operator-facing visibility surface (need #4). It makes gate/ticket/PR
  state legible to a non-coder, which is a D-005 trust mechanism, not a feature.
note: |
  OPERATOR-REQUESTED 2026-08-03 (Q-002 in fleet/state/DECISIONS.md): a graphic web page showing
  broken gates / unfinished features / code map. Operator asked for a FIRST VERSION today.

  TOOL DECISION (see D-011): a GENERATED STATIC HTML PAGE, not n8n and not Grafana-yet.
    - n8n is workflow automation ("when X, do Y") — event glue with a visual editor, NOT a
      dashboard. Rendering a status page in it means fighting it.
    - monit IS the right tool for PROCESS LIVENESS and is already partly adopted
      (fleet/watchdog/ generates monit config from fleet/state/service-registry.tsv). Use it for
      "is the service up" — do not stretch it to gates/tickets/code.
    - Grafana is the standard answer for live dashboards with history + alerting, and is the right
      upgrade LATER. It costs a server plus data sources to keep alive, and keeping services alive
      is precisely what keeps failing here.
    - A generated static page has zero runtime, nothing to keep alive, no auth, and is versioned in
      git. ~80% of the value at ~5% of the operating cost. Regenerated on each CI run and each cron
      tick it is minutes-fresh, which is what "realtime" actually needs to mean here.

  ⛔ THE HONESTY RULE — THIS IS THE WHOLE POINT OF THE TICKET ⛔
  A gate whose test has NEVER been observed to fail renders **UNPROVEN (grey)**, never green.
  Green means "checked and passing". Grey means "we cannot claim this". Red means "failing".
  A dashboard fed by unproven gates displays a GREEN LIE, and this project has that failure on
  record: 113 red-proof suites that never execute in CI, and a PASSING check reported as RED for
  weeks. If the page cannot distinguish proven-green from unproven, it is worse than no page,
  because the operator would believe it.

  DATA SOURCES — all already exist, none may be invented or estimated:
    gates          `charon.cli gate` (product), `fleet/validate_board.sh`, `fleet/checks/gate-integrity.sh scan`
    unproven set   gate-integrity's G3/G5 output + `fleet/checks/rig-ci-scope.sh` CI_SUITES allowlist
    work loss      `fleet/checks/stranded-work.sh` (currently 287 findings)
    tickets        `fleet/board/*.md` frontmatter (state, priority, owns)
    PRs            `gh api` (REST, ETag/--jq; GraphQL quota is scarce)
    code map       `graphify` graph.json (already built) + `graphify affected` for blast radius
    liveness       `fleet/state/service-registry.tsv` (+ monit where wired)

  ACCEPTANCE: the page must show tonight's REAL numbers, including the bad ones — 287 stranded
  findings, 46-of-62 draft PRs, 113 unproven red-proof suites, 7 parked providers, 851-of-861
  unpriced models. A first version that renders everything green is a FAILED first version.
