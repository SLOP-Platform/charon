tier: sonnet
difficulty: 2  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: refactor
branch: feat/review-log-fragments
depends_on:
owns: docs/REVIEW-LOG.md, docs/review-log/*, tools/render_review_log.py, tests/test_render_review_log.py
prompt: /home/stack/charon-private/prompts/fb3.md
note: SCHEDULE between waves — touches docs/REVIEW-LOG.md, so launch only when NO other
  ticket that appends a review note is in flight (else it collides on the very file it is
  retiring). Manager picks the quiet window.
