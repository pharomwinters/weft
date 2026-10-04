# Weft

*Where your data comes together.*

A free, open-source, self-hosted alternative to Grist, Baserow and NocoDB: a
spreadsheet-style interface over relational data in Postgres.

It is built to be **safe on the open internet from the moment it starts**:
every account must use two-factor authentication, there is no default
password, and nothing is reachable without a fully verified session.

This repository currently contains the **foundation**: deployment, first-run
setup, accounts with enforced TOTP, invitations, workspaces with
owner/editor/viewer roles, and an audit log. Bases, tables, the grid and
charts come next. Licence: AGPL-3.0.

## Quick start

You need Docker with Compose.

```sh
cp .env.example .env
```

Edit `.env` and replace the placeholders. The server refuses to start while
any required value is missing or unchanged.

| Variable | What to put there |
|---|---|
| `POSTGRES_PASSWORD` | A database password: `openssl rand -hex 24` |
| `DATABASE_URL` | The same password, in place of `change-me` |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `TOTP_ENCRYPTION_KEY` | `python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` |
| `PUBLIC_URL` | The address people will use, e.g. `https://grid.example.com` (or `http://localhost:8000` to try it locally) |

Then:

```sh
docker compose up -d
```

Keep `TOTP_ENCRYPTION_KEY` safe and unchanged: it encrypts every user's
authenticator secret, and losing it means every user must have their 2FA
reset.

## Creating the first admin

A fresh instance has no admin and no default credentials. Exactly one of two
routes applies:

**Setup token (the default).** At each start, while no admin exists, the
server prints a one-time token:

```sh
docker compose logs app | grep "Setup token:"
```

Open the app, and the setup page asks for that token, an email and a
password. You then set up your authenticator app straight away. Restarting
the container replaces the token.

**Admin from the environment.** Set both `INITIAL_ADMIN_EMAIL` and
`INITIAL_ADMIN_PASSWORD` in `.env` before the first start. The account is
created at startup, and at first sign-in you must set up an authenticator and
choose a new password. The setup page never appears. These two values are
only read while no admin exists, so a stale `.env` cannot reset the account;
remove them afterwards.

Once an admin exists, the setup endpoints answer 404 permanently.

## Behind a reverse proxy or tunnel

`TRUSTED_PROXY_COUNT` says how many reverse proxies sit between the internet
and the app. It decides whose address is used for the per-address login
limit (20 failures in 15 minutes block an address for 15 minutes).

- `0` (default): nothing in front, or you do not want to trust forwarded
  headers. `X-Forwarded-For` is ignored entirely.
- `1`: one proxy. The app uses the address that proxy reports and ignores
  anything a client put in the header itself.

Set it to the real number. Too high lets a client forge its address; too low
makes every visitor look like the proxy.

Example, Tailscale Funnel on the same machine:

```sh
tailscale funnel 8000
```

```
PUBLIC_URL=https://your-machine.your-tailnet.ts.net
TRUSTED_PROXY_COUNT=1
```

The per-account lockout (five consecutive failures lock an account for 15
minutes) works whatever this is set to.

## Inviting people

There is no open sign-up and no email. An instance admin (Admin → Invitations)
or a workspace owner (the workspace's Members section) creates an invitation
link and sends it however they like. A link works once and expires after 7
days. The invitee chooses a password and sets up an authenticator.

## When someone is locked out

Nothing here needs a mail server.

| Situation | What to do |
|---|---|
| Forgotten password | An admin opens Admin → Users → **Reset link** and gives the user the link (single use, 24 hours). The user still needs their authenticator. |
| Lost authenticator and recovery codes | An admin opens Admin → Users → **Reset 2FA**. The user sets up a new authenticator at their next sign-in. |
| The admin is locked out | On the server (shell access is the proof of ownership): |

```sh
docker compose exec app python backend/manage.py reset_password admin@example.com   # prints a reset link
docker compose exec app python backend/manage.py reset_2fa admin@example.com
```

Each user also gets ten single-use recovery codes when they set up their
authenticator; one of those signs them in without it.

## Local development

Tools: [uv](https://docs.astral.sh/uv/) (Python), [pnpm](https://pnpm.io/)
(Node 22+), Docker for Postgres.

```sh
docker compose -f compose.dev.yml up -d postgres   # Postgres on localhost:55433
uv sync

# Backend checks (run from the repository root)
uv run pytest -q
uv run ruff check . && uv run ruff format --check . && uv run ty check

# Run the API on :8000 with development settings
export DATABASE_URL=postgres://app:app@localhost:55433/app
export SECRET_KEY=$(openssl rand -hex 32)
export TOTP_ENCRYPTION_KEY=$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
export PUBLIC_URL=http://localhost:5173
export DJANGO_SETTINGS_MODULE=config.settings_dev
uv run python backend/manage.py bootstrap          # migrates, prints the setup token
(cd backend && uv run uvicorn config.asgi:application --reload --port 8000)

# Frontend on :5173, proxying /api to :8000
cd frontend
pnpm install
pnpm dev
pnpm test && pnpm lint && pnpm typecheck
```

To use a different Postgres for tests, put `DATABASE_URL=...` in a
git-ignored `.env.dev` at the repository root.

After changing the API, regenerate the frontend's types and commit the result
(CI fails if they are stale):

```sh
cd frontend && pnpm gen:api
```

End-to-end tests (Playwright) build the frontend and run the real server
against a scratch database named `e2e`:

```sh
cd frontend && pnpm exec playwright install chromium && pnpm e2e
```

## Layout

```
backend/    Django project: accounts, workspaces, permissions, audit, api
frontend/   React single-page app (Vite, TypeScript, Mantine)
docker/     Dockerfile and entrypoint for the single app container
docs/       Design specs and implementation plans
```
