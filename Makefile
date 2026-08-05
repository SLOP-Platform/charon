.PHONY: install dev test lint type boundary version audit demo all clean status

status:  ## interim: computed session state (git + forge). Upgraded post-§3.
	@echo "== CG status (INTERIM — reads git+forge, not the event store) =="
	@echo "branch:    $$(git rev-parse --abbrev-ref HEAD)"
	@echo "dirty:     $$(test -n \"$$(git status --porcelain)\" && echo YES || echo no)"
	@echo "worktrees:"; git worktree list
	@echo "next issue:"; gh issue list --label next --limit 5 2>/dev/null || echo "  (gh unavailable)"
	@echo "open PRs:   $$(gh pr list --state open --limit 100 2>/dev/null | wc -l)"
	@echo "main CI:    $$(gh run list --branch master --limit 1 2>/dev/null || echo n/a)"

install:
	pipx install . || pip install .

dev:
	pip install -e '.[dev,service]'

test:
	pytest -q

lint:
	ruff check src tests tools

type:
	mypy src/charon

boundary:
	python3 tools/check_boundary.py src

version:
	python3 tools/check_version.py

audit:
	pip-audit || true

# TOOL-ENABLE-RATCHET: bandit against the committed baseline floor -- fails
# only on findings NEW since .bandit-baseline.json was generated. Not wired
# into the `all`/CI gate (ruff's S-rule family already covers this ground
# there per src/charon/scanners.py); this is the standalone deeper scan.
security:
	bandit -r src -b .bandit-baseline.json

demo:
	charon run --goal "create hello" --accept "test -f hello.txt" --backend mock --autonomy L1

# The full local gate — mirrors CI.
all: boundary version lint type test

clean:
	rm -rf .charon .pytest_cache .mypy_cache **/__pycache__ build dist *.egg-info
