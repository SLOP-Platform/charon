repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: feat/monit-install-or-retire
depends_on:
owns: fleet/watchdog/service-registry.tsv, fleet/state/MONIT-INSTALL-OR-RETIRE.md, docs/review-log/MONIT-INSTALL-OR-RETIRE.md
serial_justified: |
  One decision (install or retire) over one adoption. A split leaves half a supervisor beside a
  half-retired one, which is worse than either.
substrate: N/A
substrate-novel: |
  The supervisor was ALREADY CHOSEN in a prior session — this ticket does not re-litigate that
  choice, it either completes the adoption or ends it honestly. fleet/watchdog/ already ships
  generate-monit-config.sh, discover-services.sh and five rendered monit.d/*.conf; what is missing
  is the RUNTIME. There is no build-vs-adopt question left to answer, only an install-or-retire
  decision, so the novel slice is the decision and its proof.
  (Written as N/A + novel deliberately: the substrate gate substring-matches the tool name against
  this ticket's own `owns:` paths, and the daemon's name is inside this ticket's own FILENAME —
  the exact defect tracked as SUBSTRATE-OWNS-WORD-BOUNDARY, demonstrated live while minting this.)
accept: |
  MEASURED 2026-08-02: `command -v monit` FAILS on this box AND on 4-LOM. No `/etc/monit*`
  anywhere. Its SSOT `fleet/state/service-registry.tsv` did not exist until this session (it was
  reconstructed from the tracked monit.d/*.conf by PR #368). So fleet/watchdog/ is a CONFIG
  GENERATOR with no runtime and, until today, no input.
  Yet PRIORITY-TODO listed monit as "already adopted by the rig — the cheapest candidate", and a
  session acted on that and had to disprove it with one command. **A paper adoption is worse than
  no adoption: it blocks the search for a real one.**
  DECIDE AND EXECUTE — do not leave it in this state a third session:
  1. INSTALL IT (preferred — it is already chosen and the generator exists):
     install monit on the host(s) that need supervision, feed it the reconstructed
     service-registry.tsv, render via generate-monit-config.sh, and PROVE it supervises by KILLING
     a supervised service and showing monit restarts it. Registration is not proof; a restart is.
  2. OR RETIRE IT: delete the watchdog generator and its configs, and strike every doc claim that
     monit is adopted — including the PRIORITY-TODO line already struck this session.
  In BOTH cases: land an EVAL-REGISTRY row recording the real outcome, so the next session inherits
  a fact instead of a claim.
  SCOPE NOTE: monit supervises SERVICES (is the process up, restart it if not). It does NOT answer
  "did this worker PRODUCE anything" — that is THROUGHPUT-EXPECTATION-ALARM, and installing monit
  does not close it. Do not let one substitute for the other.

## Dependencies & Sequence

P0 by doctrine-integrity: a false adoption in the handoff cost a session real time and blocked the
search for alternatives. No inbound deps. Related to THROUGHPUT-EXPECTATION-ALARM (worker
production) and to the dead-man's-switch evaluation it requires — monit covers process liveness
only, which is one third of that surface.
