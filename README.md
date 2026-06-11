# Boilerplate Lambda

This repository is a base template for AWS Lambda functions written in Python.

The goal is to keep each Lambda repository simple, independent, and standardized across the project.

This boilerplate includes:

- Python 3.14
- `uv` for dependency management
- `ruff` for linting and formatting
- `pytest` for tests
- `pre-commit` for local code checks before commits
- `debugpy` support for local debugging with VS Code
- `serverless-toolkit` for shared Lambda utilities, such as standardized logging

---

## Setup

Install dependencies:

```bash
uv sync
```

Install pre-commit hooks:

```bash
uv run pre-commit install
```

After this, Ruff will run automatically before each commit.

---

## Environment Variables

Use `.env.example` as reference:

```env
# ---------- APP VARIABLES
ENVIRONMENT=
SOURCE_NAME=

# ---------- LOG VARIABLES
POWERTOOLS_SERVICE_NAME=
POWERTOOLS_LOG_LEVEL=
POWERTOOLS_LOG_EVENT=
```

Logging is handled by `serverless-toolkit`, which uses AWS Lambda Powertools to generate structured JSON logs.

---

## Common Commands

Run lint:

```bash
make lint
```

Format code:

```bash
make format
```

Run tests:

```bash
make test
```

Package the Lambda:

```bash
make package
```

Clean generated files:

```bash
make clean
```

---

## Debugging

This project includes `debugpy` as a development dependency.

For quick debugging during tests, you can also use:

```python
breakpoint()
```

For VS Code debugging, use the local debug runner if available and place breakpoints directly in the handler or service files.

---

## Notes

This repository should contain only Lambda application code.

Infrastructure as Code should live in the global IaC repository, and shared utilities should live in `serverless-toolkit`.