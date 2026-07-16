# WEB-ROADMAP-GENERATOR

## Decision

- **roadmap-html.sh**: The existing script at `charon-private/fleet/roadmap-html.sh` was already a
  complete awk-based renderer of ROADMAP.tsv → self-contained HTML (Projects → Waves → tickets +
  descriptions + status chips). Verified: all 177 ROADMAP.tsv ticket IDs render in the output, all
  wave labels present. No changes needed.
- **end-session.sh**: The existing wiring saved HTML to `state/overnight/roadmap.html` and
  suppressed all output (`>/dev/null 2>&1`). Changed to:
  - Save to `state/roadmap.html` (durable path, not scratch)
  - Preserve the "wrote" status message
  - Print manager-facing instructions to re-publish to the durable Artifact URL
    `255411a5-edda-46c1-aded-a23b6d53811d`
- **Publish constraint**: Shell alone cannot push to claude.ai. Encoded as end-session.sh output
  text — a doctrine/checklist instruction printed at session close.
