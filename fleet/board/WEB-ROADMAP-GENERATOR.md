repo: charon-private
tier: economy
priority: 2
difficulty: 3
work_class: rig-meta
branch: feat/web-roadmap-generator
depends_on:
owns: /home/stack/charon-private/fleet/roadmap-html.sh, /home/stack/charon-private/fleet/end-session.sh
serial_justified: end-session.sh's wiring must call roadmap-html.sh's actual output/interface — the
  caller (end-session.sh) can only be written correctly once the callee (roadmap-html.sh) exists;
  building both concurrently risks end-session.sh being wired against a guessed interface.
accept: |
  A persistent, self-refreshing WEB roadmap. Build fleet/roadmap-html.sh that renders ROADMAP.tsv into the
  full-page HTML (Projects -> Waves -> tickets + descriptions + status chips; the layout already exists as a
  hand-built reference — the published Artifact roadmap, url 255411a5-edda-46c1-aded-a23b6d53811d). Then a
  SESSION-END step regenerates the HTML and RE-PUBLISHES it to the SAME artifact url (keeps the link
  durable + current). Constraint: the publish step needs the manager's Artifact tool (a shell script alone
  cannot push to claude.ai), so encode it as: end-session.sh emits the fresh HTML; a doctrine rule +
  session-end checklist has the manager re-publish to the same url. It refreshes at each close, not real-time.
  Fail-on-revert: roadmap-html.sh output must contain every ROADMAP.tsv ticket id + its wave.
scope: |
  Operator 2026-07-10: wants the roadmap web link to PERSIST across sessions AND update as tickets close/add.
  The terminal report.sh is already live-current + prints at session end; this is the WEB counterpart.
ds: Now (rig-only). FLEET project. Add its ROADMAP row when the auditor-fold is applied.
