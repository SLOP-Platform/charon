repo: charon-private
tier: economy
difficulty: 1
work_class: rig-meta
branch: chore/pyc-gitignore
owns: .gitignore
depends_on:
note: stray committed __pycache__/*.pyc files (e.g. fleet/capability/__pycache__/availability.cpython-312.pyc, flagged blocking PR #62). Add __pycache__/ + *.pyc to .gitignore and git-rm --cached any tracked ones across the rig.
accept: |
  - .gitignore ignores __pycache__/ and *.pyc; `git ls-files | grep -E '\.pyc$|__pycache__'` returns nothing.
