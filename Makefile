.PHONY: install dev test lint type boundary version audit demo all clean

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
