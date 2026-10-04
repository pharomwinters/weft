# Contributing to Weft

Thank you for wanting to help. Weft is free software under the AGPL-3.0, and
no feature is ever withheld from self-hosters.

Found a security problem? Do not open an issue: see [SECURITY.md](SECURITY.md).

## Before you start

For anything larger than a small fix, open an issue first and describe what
you want to change. Features are designed in a spec and then a plan (see
`docs/superpowers/`), and a change that cuts across those is easier to agree
on before the code exists.

## Setting up

You need [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/) with
Node 22 or newer, and Docker for Postgres. The README's
[Local development](README.md#local-development) section has the commands to
run the API, the frontend and the tests.

Python is managed with uv and Node with pnpm, both from committed lockfiles.
Please do not use pip or npm here.

## What a change needs

- **Tests.** Write the test first where you can. Backend tests run against a
  real Postgres through the HTTP API; frontend components are tested with
  Vitest and Testing Library; whole flows with Playwright.
- **All checks passing.** CI runs these on every push and pull request:

  ```sh
  # from the repository root
  uv run ruff check . && uv run ruff format --check . && uv run ty check
  uv run pytest -q

  # from frontend/
  pnpm lint && pnpm typecheck && pnpm test && pnpm build
  pnpm e2e
  ```

- **Fresh API types.** After changing an endpoint or a schema, run
  `pnpm gen:api` in `frontend/` and commit the result. CI fails if the
  generated types are stale.
- **A migration**, if you changed a model: `uv run python backend/manage.py
  makemigrations --settings config.settings_test`.

## Rules the code keeps

These hold everywhere, and reviews will check them:

- **Deny by default.** Every API endpoint requires a fully verified session
  unless it is listed in `backend/api/access.py`. Adding to that list needs a
  reason in the commit message.
- **One place decides permissions.** Endpoints call `permissions.can` or
  `permissions.require`; they never look at roles or the admin flag
  themselves.
- **Secrets stay secret.** Passwords, TOTP secrets, recovery codes and tokens
  are never logged, never written to the audit log, and never returned by
  the API after the one response that issues them. Tokens are stored only as
  hashes.
- **One error shape.** Every error response is
  `{"error": {"code", "message", "details"}}`.
- **Emails** are stored and compared trimmed and lower-cased.
- **The name** comes from one constant per side (`APP_NAME` in
  `frontend/src/constants.ts`, `ISSUER` in `backend/accounts/totp.py`).

## Commits and pull requests

- Keep a pull request to one change, with a description of what it does and
  how you checked it.
- Commit subjects follow the existing history: `feat: …`, `fix: …`,
  `test: …`, `docs: …`.
- Match the style of the code around your change; Ruff and ESLint settle the
  formatting.

## Licence

By contributing you agree that your contribution is licensed under the
AGPL-3.0, the same licence as the rest of the project.
