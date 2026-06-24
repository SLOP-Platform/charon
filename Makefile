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

demo:
	charon run --goal "create hello" --accept "test -f hello.txt" --backend mock --autonomy L1

# The full local gate — mirrors CI.
all: boundary version lint type test

clean:
	rm -rf .charon .pytest_cache .mypy_cache **/__pycache__ build dist *.egg-info
