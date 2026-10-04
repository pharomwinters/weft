# Foundation Design

Date: 2026-10-03
Status: awaiting review
Spec 1 of 4 for the first public release.

## 1. Project context

This project is a free, open-source, self-hosted alternative to Grist, Baserow and NocoDB: a spreadsheet-style interface over relational data stored in Postgres. It is licensed AGPL-3.0, and no feature is ever withheld from self-hosters.

Two things set it apart from the tools it replaces:

- **Built-in charting** with Apache ECharts, with no custom plugins needed.
- **Safe on the open internet by default.** People expose self-hosted tools through tunnels such as Tailscale Funnel. An instance of this app must be safe to expose from the moment it starts, with no configuration required to make it so.

### First public release

The first release lets a team sign in with enforced two-factor authentication, create workspaces, bases and tables with typed columns and references, edit data in a spreadsheet grid with sort and filter, and build charts from a table. It is delivered as four specs, each with its own plan and build cycle:

| # | Spec | Contents |
|---|---|---|
| 1 | **Foundation** (this document) | Project skeleton, deployment, authentication, workspaces, roles |
| 2 | Data core | Bases, real Postgres tables, row and schema API, change events, live updates |
| 3 | Grid | Spreadsheet UI built on Glide Data Grid behind an adapter |
| 4 | Charting | ECharts widgets bound to table data |

Later sub-projects, not part of the first release: Python formula engine (sandboxed), pages and linked widgets, row and column access rules, attachments, connecting to existing external databases, passkeys, single sign-on.

### Decisions that apply to every spec

- **Backend:** Python, Django for the platform, plus a separate SQL engine for user tables (spec 2). Django was chosen so that security-critical code rests on mature, audited components.
- **Frontend:** React 18, TypeScript, Vite, single-page app. React is pinned to 18 because the stable Glide Data Grid release targets it.
- **Storage:** Postgres is the app's own store. Each user table is a real Postgres table. Each base is its own Postgres schema.
- **Hierarchy:** Workspace → Base → Tables. One install is one organisation. Nothing may hard-code that, so multiple organisations stay possible.
- **Collaboration:** live updates over WebSocket, last write wins per cell (spec 2).
- **Column types in the first release:** text, long text, integer, decimal, boolean, date, date-time, choice, multiple choice, reference, reference list, auto-number (spec 2).

## 2. Scope of this spec

In scope:

- Repository layout, tooling, CI and Docker deployment
- First-run setup
- Accounts, sessions, enforced TOTP, recovery codes
- Brute-force protection
- Invitations, password reset and 2FA reset without email
- Workspaces, memberships and roles
- The permission function
- Audit log
- Frontend screens for all of the above

Out of scope: bases, tables, the grid, charts, WebSocket transport, passkeys, single sign-on, email delivery, public sharing links.

## 3. Architecture

### Deployment

Docker Compose with two containers: `app` and `postgres`. The app container runs one ASGI server (uvicorn) that serves the JSON API and the built frontend (static files via WhiteNoise). No Redis or other services. ASGI is used from the start so spec 2 can add WebSockets without changing the server.

Minimum versions: Python 3.12, Django 5.2 LTS, Postgres 16, Node 22 (build only).

### Tooling

| Purpose | Tool |
|---|---|
| Python versions, dependencies and virtual environment | uv, with a committed `uv.lock` |
| Python linting and formatting | Ruff |
| Python type checking | ty |
| Node dependencies | pnpm, with a committed `pnpm-lock.yaml` |
| Frontend linting and type checking | ESLint, `tsc` |

The Docker build and CI install from the lockfiles using these same tools, so local, CI and container environments match.

### Repository layout

```
backend/
  config/          Django project: settings, urls, asgi
  accounts/        users, sessions, TOTP, recovery codes, invitations, setup, lockout
  workspaces/      workspaces, memberships
  permissions/     can() and the role-action table
  audit/           audit events
  api/             Django Ninja routers, error handling, auth dependencies
  tests/
frontend/
  src/
    api/           generated types and a typed client
    auth/          setup, login, 2FA, invitation screens
    workspaces/    workspace list and detail
    account/       account settings
    admin/         users, invitations, audit log
docker/
docs/
```

### Units

| Unit | Responsibility | Depends on |
|---|---|---|
| `accounts` | Users, sessions, TOTP, recovery codes, invitations, reset links, first-run setup, lockout | Django auth, `django-otp`, `django-axes` |
| `workspaces` | Workspaces and memberships, last-owner rule, soft delete | `accounts` |
| `permissions` | `can(user, action, target)` | `workspaces` |
| `audit` | Record and query security events | `accounts` |
| `api` | HTTP endpoints. Every endpoint declares its required session state and calls `permissions` | all of the above |

The API is built with Django Ninja. Its OpenAPI schema is exported in CI and used to generate the frontend's TypeScript types, so the two cannot drift silently.

All Django tables live in a Postgres schema named `platform`, leaving other schemas free for bases.

## 4. Authentication

### Session states

| State | How it is reached | What it can reach |
|---|---|---|
| Anonymous | No session | Login, setup, invitation acceptance, reset-link redemption |
| Partial | Password correct | TOTP verify, TOTP enrolment, forced password change, logout |
| Verified | Second factor passed | Everything else, subject to roles |

Endpoints require a verified session unless they are explicitly marked `anonymous` or `partial`. A test walks every registered route and fails if an unmarked route responds to an anonymous or partial session with anything other than 401. A new endpoint therefore cannot be exposed by accident.

A partial session expires after 10 minutes. A verified session expires after 14 days without activity.

### Login

1. Email and password. Emails are unique and compared case-insensitively.
2. A TOTP code or a recovery code.
3. If the account has `must_change_password` set, a forced password change before the session becomes verified.

An account with no confirmed TOTP device is sent to enrolment after step 1 and cannot skip it. There is no setting, for any role, that disables the second factor.

### TOTP enrolment

- The server generates a secret and shows it as a QR code and as text.
- The device is confirmed only when the user submits a valid code.
- On confirmation the server shows ten single-use recovery codes, once.
- TOTP secrets are encrypted at rest with a key from configuration. Recovery codes are stored hashed.
- A TOTP code that has been accepted cannot be accepted again within its validity window.
- A user can re-enrol from account settings, which replaces the device and regenerates recovery codes. This requires a current TOTP or recovery code.

`django-otp` supplies the TOTP algorithm and verification. Because it stores secrets and static tokens unencrypted by default, this project defines its own device and recovery-code models on top of it to meet the two storage rules above.

### Passwords

Argon2 hashing. Minimum length 12. Rejected if found in Django's common-password list or if too similar to the user's email.

### Brute-force protection

- Five consecutive failures against one account, at either the password or the code step, lock that account for 15 minutes.
- Twenty failures from one IP address within 15 minutes block that address for 15 minutes.
- Successful login resets the account counter.

Per-IP limits need the real client address. A `TRUSTED_PROXY_COUNT` setting (default 0) says how many reverse proxies sit in front of the app; forwarded-for headers are ignored unless it is set. Per-account lockout works regardless of this setting.

Accepted trade-off: an attacker who knows an email address can keep that account temporarily locked. The lockout is short and is recorded in the audit log.

### Responses that do not leak

Login returns the same response and takes comparable time whether or not the email exists. Invitation and reset-link redemption return the same error for unknown, used and expired tokens.

### Sessions

- Server-side sessions, stored in the database.
- Cookie is HttpOnly and SameSite=Lax. It is marked Secure when `PUBLIC_URL` is https.
- CSRF protection on every state-changing request.
- Each session records IP address, user agent, creation time and last-seen time. Users can list and revoke their own sessions.
- Changing a password, resetting a password or resetting 2FA ends all of that user's other sessions.

### Joining and recovery without email

Nothing in this spec depends on a mail server.

| Situation | Mechanism |
|---|---|
| New user | An instance admin or a workspace owner creates an invitation link. Single-use, expires after 7 days. An owner's invitation joins the invitee to that workspace with a chosen role. The invitee sets a password and enrols TOTP. |
| Forgotten password | An instance admin generates a reset link. Single-use, expires after 24 hours. Redeeming it sets a new password; the second factor is still required. |
| Lost authenticator and recovery codes | An instance admin resets that user's second factor. The user re-enrols at next login. |
| Admin locked out | `manage.py reset-2fa <email>` and `manage.py reset-password <email>` run on the server. Shell access to the host is the proof of ownership. |

Invitation and reset tokens are random, at least 256 bits, and stored hashed. Open sign-up does not exist in this release.

An instance admin can deactivate a user, which ends their sessions and blocks login without deleting their records.

## 5. First-run setup

A fresh install has no admin. Two routes create one, and exactly one applies:

- **Env-provided admin.** If `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` are both set and no admin exists, the server creates that account at startup with `must_change_password` set. The setup page never appears. At first login the admin changes the password and enrols TOTP.
- **Setup token.** Otherwise, while no admin exists, the server generates a one-time token at each start and prints it to the logs. The setup page requires the token to create the admin, who then enrols TOTP immediately.

Rules:

- There is no default credential. A missing or empty password means the token route.
- The env values are read only when no admin exists, so a stale env file cannot reset or re-create the account.
- The setup endpoints return 404 permanently once an admin exists.
- The setup token is held hashed, and is subject to the per-IP failure limit.

## 6. Workspaces and roles

### Data model

| Model | Key fields |
|---|---|
| `User` | email, password hash, `is_instance_admin`, `must_change_password`, `is_active` |
| `TotpDevice` | user, encrypted secret, confirmed, last accepted time step |
| `RecoveryCode` | user, code hash, used-at |
| `UserSession` | user, session key, IP, user agent, created, last seen |
| `Invitation` | token hash, created-by, optional workspace and role, expires-at, used-at, used-by |
| `ResetLink` | token hash, user, created-by, expires-at, used-at |
| `Workspace` | name, created-by, deleted-at |
| `Membership` | user, workspace, role; unique on user and workspace |
| `AuditEvent` | time, actor, event type, target, IP, details (JSON) |

### Roles

Instance admin is a flag on the user. Owner, editor and viewer are held on a membership.

| Action | Instance admin | Owner | Editor | Viewer |
|---|---|---|---|---|
| `instance.manage_users` | yes | | | |
| `instance.create_invitation` | yes | | | |
| `instance.view_audit_log` | yes | | | |
| `workspace.create` | any verified user | | | |
| `workspace.view` | yes | yes | yes | yes |
| `workspace.rename` | yes | yes | | |
| `workspace.manage_members` | yes | yes | | |
| `workspace.invite` | yes | yes | | |
| `workspace.delete` | yes | yes | | |
| `workspace.restore` | yes | yes | | |

Editor and viewer are identical within this spec. They diverge in spec 2, which adds base and data actions to the same table.

### Rules

- The user who creates a workspace becomes its owner.
- A workspace always has at least one owner. Removing or demoting the last owner is refused.
- The instance always has at least one active admin. Demoting or deactivating the last one is refused.
- Instance admins can see and manage every workspace, so none is orphaned.
- Deleting a workspace sets `deleted_at`. It disappears from normal lists and can be restored for 30 days. Permanent removal after that is left to spec 2, which knows what a workspace contains.

### The permission function

`can(user, action, target) -> bool`, where the target is the instance or a workspace. Actions are named constants and one table maps roles to actions. Endpoints call `can` and never inspect roles themselves. Spec 2 adds bases as a target type, and later access rules extend the same function.

## 7. Audit log

Recorded events: login success, login failure, lockout, logout, TOTP enrolment, recovery code used, password changed, reset link created and used, 2FA reset, invitation created and accepted, user deactivated and reactivated, admin flag changed, membership added, changed and removed, workspace created, deleted and restored, setup completed.

Each event stores the time, the acting user where known, the target, the IP address and event-specific details. Secrets, passwords and tokens are never written to it. Instance admins can view and filter the log. Events are append-only through the application.

## 8. Configuration

Read from environment variables, normally an env file used by Docker Compose.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection |
| `SECRET_KEY` | yes | Django signing key |
| `TOTP_ENCRYPTION_KEY` | yes | Encrypts TOTP secrets at rest |
| `PUBLIC_URL` | yes | External URL; sets allowed host, CSRF origin and the cookie Secure flag |
| `TRUSTED_PROXY_COUNT` | no, default 0 | Reverse proxies in front of the app |
| `INITIAL_ADMIN_EMAIL` | no | Env-provided admin |
| `INITIAL_ADMIN_PASSWORD` | no | Env-provided admin |

The server refuses to start if a required value is missing or still equal to the value in the example env file. It logs a warning at startup if `PUBLIC_URL` is plain http and not a localhost address. Debug mode cannot be enabled through the production container's configuration.

## 9. API

All endpoints are under `/api/v1/`. Groups:

- `setup`: status, create admin
- `auth`: login, verify code, enrol start and confirm, change password, logout, current session
- `account`: profile, sessions list and revoke, re-enrol
- `invitations`: create, list, revoke, inspect by token, accept
- `admin/users`: list, deactivate, reactivate, set admin flag, create reset link, reset 2FA
- `admin/audit`: list with filters
- `workspaces`: list, create, get, rename, delete, restore
- `workspaces/{id}/members`: list, add existing user, change role, remove

Errors share one shape:

```json
{ "error": { "code": "last_owner", "message": "A workspace must keep at least one owner.", "details": {} } }
```

`code` is a stable machine-readable string. Status codes: 400 validation, 401 no adequate session, 403 not permitted, 404 not found or not visible, 409 rule conflict, 429 locked out or rate limited. A 401 states whether the session is anonymous or partial, and for a partial session which step is needed next.

## 10. Frontend

Screens:

- Setup (token entry and admin creation)
- Login, TOTP verify with a recovery-code option
- TOTP enrolment and recovery-code display, with a required "I have saved these" confirmation
- Forced password change
- Invitation acceptance
- Workspace list; workspace detail with members, roles and an empty bases list
- Account settings: password, active sessions, re-enrol 2FA
- Admin: users, invitations, audit log

Behaviour:

- A single typed API client handles CSRF and errors.
- Any 401 routes the user to the step the response names: login, code entry, enrolment or password change.
- Route guards mirror the server's session states but are a convenience only; the server is the authority.
- Forms show field-level validation errors from the API's `details`.

## 11. Testing

- **Backend:** pytest against a real Postgres. Auth is tested end to end through the HTTP API: both setup routes, enrolment, login, lockout thresholds, TOTP replay, recovery-code reuse, expired and reused invitations and reset links, session revocation, forced password change, last-owner and last-admin rules.
- **Deny by default:** the route-walking test from section 4.
- **Permissions:** every role against every action, checked against the table in section 6.
- **Configuration:** startup refusal for missing and placeholder secrets.
- **Frontend:** component tests for forms and guards (Vitest), and Playwright browser tests for setup, enrolment, login, invitation and workspace membership.
- **CI:** on every push, runs backend and frontend tests, linting and format checks (Ruff, ESLint), type checks (ty, `tsc`), and a check that the generated API types are up to date.

## 12. Done when

- `docker compose up` on a clean machine, with only the env file filled in, gives a working instance.
- An admin can be created by either setup route, and by no other means.
- No data-bearing endpoint responds without a verified session.
- A user can be invited, join, enrol TOTP, and be given a role in a workspace.
- Every recovery path in section 4 works without email.
- All tests in section 11 pass in CI.
