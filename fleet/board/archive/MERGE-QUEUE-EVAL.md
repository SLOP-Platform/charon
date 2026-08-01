repo: charon-private
tier: strong
difficulty: 2
priority: 0
work_class: design-review
branch: eval/merge-queue
owns: fleet/state/MERGE-QUEUE-EVAL.md
depends_on:
source: fleet/state/ADOPT-EVAL-CONTROL-PLANE.md §4 "Category 3 — Merge-queue / admission" (prior
  WLS-5 spike settled the PUBLIC-repo case; this ticket is a focused, standalone follow-up eval
  scoped to picking/confirming a specific tool and covering the PRIVATE-rig case honestly).
work_class_note: design-review — a recommendation + EVAL-REGISTRY row, not a build ticket. If the
  verdict is ADOPT for a given repo, enabling it is a small separate follow-on (mostly
  configuration, not code).
note: |
  Prior research (WORKLOOP-INTEGRITY-STACK-SPIKE, ADOPT-EVAL-CONTROL-PLANE §4) already settled:
  GitHub-native merge queue is free + ADOPT-ready on the PUBLIC product mirror
  (SLOP-Platform/charon); Mergify/Aviator are REJECTED as paid-for-private + redundant with free
  native. This ticket's job is NARROWER and NET-NEW: (a) confirm/execute enabling GitHub-native
  merge queue on the public repo (the prior spike settled the verdict but per the state audit
  this was never actually turned on — confirm branch-protection state directly, do not trust the
  doc), and (b) name the honest answer for the PRIVATE rig (charon-private) given GitHub-native
  merge queue requires a paid plan or org context on private repos, and the fleet's own direction
  is Gitea-primary (git-hosting-gitea-primary memory) — evaluate Gitea's own merge-queue-adjacent
  primitives (protected-branch + required-status merge, or a pre-receive hook) as the actual
  private-repo path, not a second SaaS purchase. [[research-posture-solution-seeking]]
  [[evaluate-tools-by-code-not-stars]]
accept: |
  - fleet/state/MERGE-QUEUE-EVAL.md: (a) verify (not assume) the current branch-protection /
    merge-queue state on the public product repo via `gh api` against the real repo — record
    the actual observed state, enable it if it is confirmed off; (b) a real comparison for the
    PRIVATE rig between GitHub-native merge queue (paid-plan-gated), Mergify/Aviator/bors
    (SaaS, paid-for-private, redundant per prior verdict — re-confirm, don't just cite), and the
    Gitea-planned pre-receive/protected-branch path — with an honest verdict for what actually
    keeps branches from falling behind master on the rig TODAY (land.sh's own rebase-before-land
    discipline may already be the de facto merge-queue for the private repo — name that
    explicitly if true, rather than manufacturing a gap that doesn't exist).
  - EVAL-REGISTRY row: append (or draft for the manager to append — avoid an owns-collision with
    FAKTORY-TRIAL or any other ticket over fleet/state/EVAL-REGISTRY.md by not claiming that file
    in owns:) `<chosen tool/mechanism> | merge-queue / admission (public + private) | <date> |
    <verdict> | aligned | <reason> | fleet/state/MERGE-QUEUE-EVAL.md | prior WLS-5 verdict`.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
scope: |
  Recommendation + registry row only. Does not modify branch-protection settings beyond what
  accept criteria (a) explicitly calls for (turning ON an already-settled, previously-verdicted
  public-repo setting), and does not build a Gitea pre-receive hook (a follow-on ticket if that
  path is the verdict).
ds: |
  ## Dependencies & sequence
  No depends_on — design/eval only, owns one new verdict doc, no code, no owns-collision with
  any other ticket in this wave (disjoint from FAKTORY-TRIAL's fleet/state/FAKTORY-TRIAL.md).
