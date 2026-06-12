.PHONY: install lint format test package clean

install:
	uv sync --all-groups

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff check src tests --fix
	uv run ruff format src tests

test:
	uv run pytest

package:
	rm -rf build dist
	mkdir -p build dist
	uv pip install \
		--target build \
		--python .venv/bin/python \
		.
	cp -r src/* build/
	cd build && zip -r ../dist/download-lambda.zip .

clean:
	rm -rf build dist .pytest_cache .ruff_cache
