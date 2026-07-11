tier: economy
difficulty: 2
work_class: ci-infra
branch: feat/repo-decl-central
depends_on:
owns: /home/stack/charon-private/fleet/_lib.sh, /home/stack/charon-private/fleet/handoff.sh, /home/stack/charon-private/fleet/retire-done.sh, /home/stack/charon-private/fleet/handoff-check.sh, /home/stack/charon-private/fleet/land-needs-push.sh
accept: |
  ONE canonical declaration of the two repos, sourced everywhere. Add to _lib.sh:
    PRODUCT_REPO="${CHARON_PRODUCT_REPO:-/home/stack/code/charon}"  (public SLOP-Platform/charon)
    FLEET_REPO="${CHARON_FLEET_REPO:-/home/stack/charon-private}"    (private Nnyan/charon-private)
  Every rig tool that currently HARDCODES /home/stack/code/charon (handoff.sh:16, retire-done.sh:57,
  handoff-check.sh:50/69, land-needs-push.sh) sources _lib.sh and uses PRODUCT_REPO/FLEET_REPO instead.
  Each tool that reasons about "a repo" must state WHICH repo explicitly (no assumed cwd).
  Fail-on-revert: a test that sets CHARON_PRODUCT_REPO to a temp path and asserts a consumer (e.g.
  retire-done / handoff-check) actually targets it, not the hardcoded default.
scope: |
  ROOT CAUSE (found 2026-07-10): the product/fleet split is load-bearing but the coupling is implicit —
  the product path is re-declared/hardcoded across ~7 rig files with inconsistent names. This is the
  origin of the recurring "wrong-repo" bug class: done-merge gate checked the PRODUCT repo for FLEET
  tickets (item-3 false reds); the fleet handoff gate runs PRODUCT-shaped pytest/ruff in the FLEET repo
  (F21/F24). Centralizing the declaration removes the whole class.
ds: Now (rig-only, disjoint from product). No product-repo change. Low collision (rig scripts only).
