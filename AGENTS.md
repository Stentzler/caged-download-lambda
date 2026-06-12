# Project Architecture

## Overview

This repository contains one AWS Lambda that checks the downloaded-file
registry, downloads one Novo CAGED FTP archive, uploads it to S3, and records
the completed transfer in DynamoDB.

Follow the global `clean-code` skill for general implementation quality. The
rules below describe this repository's architecture and local conventions.

## Structure

- `src/handler.py`: Lambda entry point and dependency wiring. Keep it thin;
  delegate business behavior to the service.
- `src/service.py`: FTP traversal, registry comparison, response construction,
  and CAGED-specific business rules.
- `src/settings.py`: Environment-backed runtime configuration.
- `src/exceptions.py`: Domain-specific exceptions and their context.
- `tests/`: Unit tests using fakes for FTP, DynamoDB, and Lambda dependencies.
- `events/`: Sample invocation payloads.
- `sample/`: Local development fixtures only.
- `debug_handler.py`: Local Lambda runner with local AWS defaults and a simulated
  Lambda context. Do not import it from production code.

## Shared Toolkit

Use `serverless-toolkit` for reusable, application-agnostic capabilities such
as AWS client/resource creation, logging, observability, and Lambda middleware.

Keep CAGED-specific rules in this repository. Do not move domain behavior into
the toolkit merely to reduce a small amount of local code.

## Implementation Conventions

- Keep `handler.py` limited to dependency setup, logging, error boundaries, and
  invoking the service.
- Inject external dependencies into services when practical so tests do not
  require network or AWS access.
- Read configuration through `Settings`; avoid scattered environment lookups.
- Preserve the Lambda response contract unless a change is explicitly required.
- Add focused tests for new business rules and response fields.
- Do not add production behavior exclusively to `debug_handler.py`.

## Validation

Run before finishing code changes:

```bash
uv run pytest
uv run ruff check .
```

Use `uv run python debug_handler.py` for local end-to-end debugging when the
required local services are available.
