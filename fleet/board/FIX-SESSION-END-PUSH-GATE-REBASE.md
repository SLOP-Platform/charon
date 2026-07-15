repo: charon-private
tier: economy
difficulty: 1
work_class: rig-meta
branch: feat/session-end-push-gate
owns: fleet/end-session.sh, fleet/tests/test_end_session_push_gate.sh
depends_on:
note: PR #62 work is COMPLETE (reviewer verified 22/22 fail-on-revert) but the branch is CONFLICTING with master + carries a stray committed fleet/capability/__pycache__/*.pyc. Rebase onto master, resolve, drop the .pyc, re-push so it lands.
accept: |
  - feat/session-end-push-gate rebased clean onto master; no __pycache__/*.pyc committed.
  - bash fleet/tests/test_end_session_push_gate.sh passes; PR #62 mergeable.
