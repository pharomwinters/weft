# Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A deployable instance where an admin is created safely on first run, users join by invitation, every account must pass TOTP, and workspaces with owner/editor/viewer roles can be managed.

**Architecture:** A Django project (`backend/`) exposes a JSON API under `/api/v1/` through Django Ninja. Sessions move through anonymous → partial → verified; every endpoint demands a verified session unless explicitly listed otherwise. A React 18 single-page app (`frontend/`) consumes the API through types generated from its OpenAPI schema. One container serves both, next to Postgres.

**Tech Stack:** Python 3.12+, Django 5.2 LTS, Django Ninja, psycopg 3, argon2-cffi, django-otp (TOTP algorithm only), django-axes, cryptography (Fernet), uvicorn, WhiteNoise, pytest, pytest-django, time-machine · React 18, TypeScript, Vite, React Router 6, TanStack Query, Mantine, qrcode.react, openapi-typescript, Vitest, Testing Library, Playwright · uv, pnpm, Ruff, ty, ESLint · Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-03-foundation-design.md`. Read it before starting any task.

## Global Constraints

- Python is managed with uv (`uv.lock` committed); Node with pnpm (`pnpm-lock.yaml` committed). Lint and format with Ruff, type-check with ty. Never use pip, npm, mypy or black.
- Minimum versions: Python 3.12, Django 5.2 LTS, Postgres 16, Node 22. React is pinned to 18.
- All backend commands run from `backend/` as `uv run …`; all frontend commands from `frontend/` as `pnpm …`.
- Backend tests need Postgres: `docker compose -f compose.dev.yml up -d postgres` (created in Task 1).
- Every API endpoint requires a verified session unless it is listed in `api/access.py` (Task 5). Adding to that list needs a reason in the commit message.
- Endpoints call `permissions.can` / `permissions.require`; they never inspect roles or `is_instance_admin` directly.
- Every error response has the shape `{"error": {"code", "message", "details"}}`.
- Passwords, TOTP secrets, recovery codes and tokens are never logged, never written to the audit log, and never returned by the API after the single response that issues them.
- Tokens (invitation, reset, setup) are `secrets.token_urlsafe(32)`, stored as a SHA-256 hex digest.
- Emails are stored and compared as `email.strip().lower()`.
- `django.contrib.admin` is not installed.
- Licence is AGPL-3.0. The product has no name yet: use no product name in code; UI copy and README use the placeholder constant `APP_NAME = "Untitled"` defined once per side.
- Third-party API names in this plan (django-axes settings, `django_otp.oath.TOTP`, Ninja's schema export) are written from memory. Confirm each against the installed version. If one differs, keep the behaviour the tests specify and note the change in the commit message.
- After each task: `uv run ruff check . && uv run ruff format --check . && uv run ty check` (backend) or `pnpm lint && pnpm typecheck` (frontend) must pass before committing.

## Review Focus

1. **Email variants.** `" Adam@Example.COM "` and `adam@example.com` are one account at login, invitation acceptance, member lookup and lockout counting. (Tests in Tasks 2, 4, 10.)
2. **Forged `X-Forwarded-For`.** With `TRUSTED_PROXY_COUNT=0` the header is ignored; with a count of 1, extra attacker-supplied entries on the left do not change the address used. An attacker cannot dodge the per-IP block by rotating the header. (Task 4.)
3. **Malformed codes.** A TOTP or recovery code with spaces, a leading zero, letters, or 500 characters is a normal failure or success, never a 500. `"012 345"` equals `"012345"`. (Task 6.)
4. **Oversized input.** A 1 MB password or email is rejected with 400 before any hashing happens. (Task 2.)
5. **Racing removals.** Two simultaneous requests that each remove one of the last two owners cannot leave a workspace with none. (Task 9.)

## File Structure

```
compose.dev.yml               Postgres for local development and tests
docker-compose.yml            Production stack: app + postgres
.env.example
LICENSE  README.md  .gitignore
.github/workflows/ci.yml
docker/Dockerfile  docker/entrypoint.sh
backend/
  pyproject.toml  uv.lock  manage.py
  config/     env.py (config loading and validation), settings.py, settings_dev.py,
              settings_test.py, urls.py, asgi.py, middleware.py (security headers), spa.py
  accounts/   models.py, passwords.py, net.py, throttle.py, sessions.py, totp.py,
              recovery.py, tokens.py, setup.py, services.py,
              management/commands/{bootstrap,reset_2fa,reset_password}.py
  audit/      models.py, events.py, service.py
  permissions/  actions.py, core.py
  workspaces/ models.py, services.py
  api/        api.py, errors.py, access.py, auth.py, schemas.py,
              routers/{setup,auth,account,invitations,admin_users,admin_audit,workspaces}.py
  tests/      conftest.py, test_*.py (one file per task area)
frontend/
  package.json  pnpm-lock.yaml  vite.config.ts  openapi.json
  src/
    main.tsx  App.tsx  routes.tsx  constants.ts
    api/        schema.d.ts (generated), client.ts, hooks.ts
    auth/       SessionProvider.tsx, guards.tsx, SetupPage.tsx, LoginPage.tsx, VerifyPage.tsx,
                EnrolPage.tsx, RecoveryCodes.tsx, ForcedPasswordPage.tsx,
                InvitationPage.tsx, ResetPage.tsx
    workspaces/ WorkspaceListPage.tsx, WorkspaceDetailPage.tsx, MembersTable.tsx
    account/    AccountPage.tsx
    admin/      UsersPage.tsx, InvitationsPage.tsx, AuditLogPage.tsx
    layout/     Shell.tsx
  e2e/          *.spec.ts, helpers.ts
scripts/e2e-server.sh
```

---

### Task 1: Backend skeleton, configuration and error shape

**Files:**
- Create: `backend/pyproject.toml`, `backend/manage.py`, `backend/config/{__init__,env,settings,settings_dev,settings_test,urls,asgi,middleware}.py`, `backend/api/{__init__,api,errors}.py`, `backend/tests/{__init__,conftest,test_config,test_errors,test_platform_schema}.py`, `compose.dev.yml`, `.env.example`, `.gitignore`, `LICENSE` (AGPL-3.0 text)

**Interfaces:**
- Produces:
  - `config.env.Config` (frozen dataclass): `database_url: str`, `secret_key: str`, `totp_encryption_key: str`, `public_url: str`, `trusted_proxy_count: int`, `initial_admin_email: str | None`, `initial_admin_password: str | None`
  - `config.env.load_config(environ: Mapping[str, str]) -> Config`, raising `config.env.ConfigError` whose message names the offending variable
  - `config.env.EXAMPLE_VALUES: dict[str, str]` — the four required values exactly as they appear in `.env.example`
  - `api.api.api: NinjaAPI`, mounted at `/api/v1/`, created with `docs_url=None, openapi_url=None`
  - `api.errors.ApiError(status: int, code: str, message: str, details: dict | None = None)`
  - `GET /api/v1/health` → `{"status": "ok"}`
  - Fixture `api_client` in `tests/conftest.py`: object with `get/post/patch/put/delete(path, json=None)` that prefixes `/api/v1`, sends JSON, and returns Django's test response

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
VALID = {"DATABASE_URL": "postgres://u:p@h/db", "SECRET_KEY": "k" * 50,
         "TOTP_ENCRYPTION_KEY": Fernet.generate_key().decode(),
         "PUBLIC_URL": "https://grid.example.com"}

def test_valid_config_defaults():
    cfg = load_config(VALID)
    assert cfg.trusted_proxy_count == 0
    assert cfg.initial_admin_email is None and cfg.initial_admin_password is None

@pytest.mark.parametrize("key", list(VALID))
def test_missing_or_empty_required_value_refused(key):
    for bad in ({k: v for k, v in VALID.items() if k != key}, {**VALID, key: ""}):
        with pytest.raises(ConfigError, match=key):
            load_config(bad)

@pytest.mark.parametrize("key", list(VALID))
def test_example_value_refused(key):
    with pytest.raises(ConfigError, match=key):
        load_config({**VALID, key: EXAMPLE_VALUES[key]})

def test_example_values_match_env_example_file():
    text = (REPO_ROOT / ".env.example").read_text()
    for key, value in EXAMPLE_VALUES.items():
        assert f"{key}={value}" in text

def test_short_secret_key_refused():          # fewer than 32 characters
def test_invalid_fernet_key_refused():
def test_public_url_must_be_http_or_https():
def test_empty_initial_admin_password_is_none():
    cfg = load_config({**VALID, "INITIAL_ADMIN_EMAIL": "a@b.co", "INITIAL_ADMIN_PASSWORD": ""})
    assert cfg.initial_admin_password is None
def test_production_settings_hard_code_debug_false(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "1")   # import config.settings fresh; assert DEBUG is False

# tests/test_errors.py
def test_health(api_client):
    assert api_client.get("/health").json() == {"status": "ok"}
def test_unknown_api_route_is_json_404(api_client):
    r = api_client.get("/nope"); assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
def test_api_error_shape():      # a test-only route raising ApiError(409, "x", "msg", {"a": 1})
    assert r.json() == {"error": {"code": "x", "message": "msg", "details": {"a": 1}}}
def test_validation_error_shape():  # test-only route with a required body field, posted empty
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation"
    assert "name" in r.json()["error"]["details"]
def test_security_headers(api_client):
    r = api_client.get("/health")
    assert r["X-Frame-Options"] == "DENY" and r["Referrer-Policy"] == "no-referrer"
    assert "default-src 'self'" in r["Content-Security-Policy"]

# tests/test_platform_schema.py
def test_django_tables_live_in_platform_schema(db):
    # query information_schema.tables for 'django_migrations'; assert table_schema == 'platform'
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest -q` → collection errors (modules missing).

- [ ] **Step 3: Implement**
  - `pyproject.toml`: dependencies from Tech Stack; dev group pytest, pytest-django, time-machine, ruff, ty. `[tool.pytest.ini_options] DJANGO_SETTINGS_MODULE = "config.settings_test"`.
  - `compose.dev.yml`: `postgres:16`, port 5432, user/password/db all `app`.
  - `.env.example`: all variables from spec section 8; required ones set to obvious placeholders (`SECRET_KEY=change-me`, etc.); a comment gives the command that generates a Fernet key.
  - `settings.py`: calls `load_config(os.environ)`; `DEBUG = False` literally; `DATABASES` from `database_url` with `OPTIONS={"options": "-c search_path=platform"}`; `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` from `public_url`; `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`/HSTS on when `public_url` is https; Argon2 first in `PASSWORD_HASHERS`; logs a warning when `public_url` is http and the host is not `localhost`/`127.0.0.1`.
  - `settings_dev.py`: `from .settings import *`, `DEBUG` from `DJANGO_DEBUG`. `settings_test.py`: sets `os.environ` defaults (DB `postgres://app:app@localhost:5432/app`) before importing `settings`, and switches to a fast password hasher.
  - A `pre_migrate` receiver runs `CREATE SCHEMA IF NOT EXISTS platform`.
  - `api/errors.py`: exception handlers on `api` mapping `ApiError`, Ninja's validation error (→ 400 `validation`, `details` keyed by field name), `Http404` (→ `not_found`). `config/urls.py` returns the JSON 404 for any unmatched `/api/` path.
  - `config/middleware.py`: sets `Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'` and `Referrer-Policy: no-referrer`.

- [ ] **Step 4: Run to verify they pass** — `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: backend skeleton, config validation, error shape"`

---

### Task 2: User model and passwords

**Files:**
- Create: `backend/accounts/{__init__,apps,models,passwords}.py`, migration, `backend/tests/test_users.py`
- Modify: `backend/config/settings.py` (`AUTH_USER_MODEL = "accounts.User"`, validators), `backend/tests/conftest.py`

**Interfaces:**
- Produces:
  - `accounts.models.User(AbstractBaseUser)`: `email` (unique, `USERNAME_FIELD`), `is_instance_admin: bool = False`, `must_change_password: bool = False`, `is_active: bool = True`, `created_at`
  - `accounts.models.normalize_email(raw: str) -> str`
  - `User.objects.create_user(email: str, password: str, **extra) -> User`
  - `accounts.passwords.validate_new_password(password: str, user: User | None = None) -> None`, raising `ApiError(400, "validation", …, {"password": [messages]})`
  - `accounts.passwords.MAX_PASSWORD_LENGTH = 1024`, `MAX_EMAIL_LENGTH = 254`
  - Fixture `make_user(email="u@example.com", password="correct horse battery", *, admin=False, must_change=False, active=True) -> User`

- [ ] **Step 1: Write the failing tests**

```python
def test_email_normalised_on_create(db):
    u = User.objects.create_user(" Adam@Example.COM ", "correct horse battery")
    assert u.email == "adam@example.com"
def test_email_unique_case_insensitive(db, make_user):
    make_user("a@example.com")
    with pytest.raises(IntegrityError): make_user("A@Example.com")
def test_password_minimum_length_12():
    with pytest.raises(ApiError): validate_new_password("short1234567"[:11])
    validate_new_password("x9!kq-Plm2#w")            # 12 characters, passes
def test_common_password_rejected():        # "password123456"
def test_password_similar_to_email_rejected(make_user):  # user adamsmith@example.com, password "adamsmith2026"
def test_oversized_password_rejected_without_hashing(monkeypatch):
    monkeypatch.setattr("django.contrib.auth.hashers.make_password", boom)
    with pytest.raises(ApiError) as e: validate_new_password("a" * 1_000_000)
    assert e.value.status == 400
def test_production_hasher_is_argon2():
    assert prod_settings.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_users.py -q`
- [ ] **Step 3: Implement** the model, manager and `validate_new_password`. Uniqueness is a `UniqueConstraint(Lower("email"))`. Validators: minimum length 12, Django's `CommonPasswordValidator`, `UserAttributeSimilarityValidator` on `email`, and the length ceiling checked first.
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit** — `git commit -m "feat: user model and password rules"`

---

### Task 3: Audit log

**Files:**
- Create: `backend/audit/{__init__,apps,models,events,service}.py`, migration, `backend/tests/test_audit.py`

**Interfaces:**
- Consumes: `accounts.net.client_ip` does not exist yet; until Task 4, `record` reads `request.META["REMOTE_ADDR"]`. Task 4 swaps it.
- Produces:
  - `audit.events`: string constants `LOGIN_SUCCESS, LOGIN_FAILURE, LOCKOUT, LOGOUT, TOTP_ENROLLED, RECOVERY_CODE_USED, PASSWORD_CHANGED, RESET_LINK_CREATED, RESET_LINK_USED, TWOFA_RESET, INVITATION_CREATED, INVITATION_ACCEPTED, USER_DEACTIVATED, USER_REACTIVATED, ADMIN_FLAG_CHANGED, MEMBERSHIP_ADDED, MEMBERSHIP_CHANGED, MEMBERSHIP_REMOVED, WORKSPACE_CREATED, WORKSPACE_DELETED, WORKSPACE_RESTORED, SETUP_COMPLETED`; each value is the lower-case name
  - `audit.models.AuditEvent`: `time`, `actor` (FK User, null, `SET_NULL`), `event: str`, `target_type: str`, `target_id: str`, `ip: str | None`, `details: dict`
  - `audit.service.record(event: str, *, request=None, actor: User | None = None, target: Model | None = None, details: dict | None = None) -> AuditEvent`
  - `audit.service.FORBIDDEN_DETAIL_KEYS = {"password", "new_password", "code", "token", "secret"}`

- [ ] **Step 1: Write the failing tests**

```python
def test_record_stores_actor_target_ip(db, make_user, rf):
    u = make_user(); req = rf.get("/", REMOTE_ADDR="203.0.113.9")
    e = record(events.LOGIN_SUCCESS, request=req, actor=u, target=u)
    assert (e.actor, e.target_type, e.target_id, e.ip) == (u, "user", str(u.pk), "203.0.113.9")
def test_forbidden_detail_key_raises(db):
    with pytest.raises(ValueError): record(events.LOGIN_FAILURE, details={"password": "x"})
def test_events_are_append_only(db):
    e = record(events.LOGOUT)
    with pytest.raises(RuntimeError): e.save()
    with pytest.raises(RuntimeError): e.delete()
def test_event_survives_actor_deletion(db, make_user):   # actor becomes None, row remains
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_audit.py -q`
- [ ] **Step 3: Implement.** `target_type` is the model's lower-case class name.
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit** — `git commit -m "feat: audit log"`

---

### Task 4: Client address and brute-force protection

**Files:**
- Create: `backend/accounts/net.py`, `backend/accounts/throttle.py`, migration (`IpFailure`), `backend/tests/test_throttle.py`
- Modify: `backend/config/settings.py`, `backend/audit/service.py` (use `client_ip`)

**Interfaces:**
- Consumes: `Config.trusted_proxy_count`, `audit.service.record`
- Produces:
  - `accounts.net.client_ip(request) -> str`
  - `accounts.throttle.is_blocked(request, email: str | None) -> bool` — true if the account (when given) or the request's address is locked
  - `accounts.throttle.record_failure(request, email: str | None) -> None` — counts against the account (when given) and the address; records `LOGIN_FAILURE`, and `LOCKOUT` when a threshold is first crossed
  - `accounts.throttle.record_success(request, email: str) -> None` — clears the account counter
  - `accounts.throttle.reset_account(email: str) -> None`
  - Constants: `ACCOUNT_LIMIT = 5`, `IP_LIMIT = 20`, `WINDOW = timedelta(minutes=15)`

- [ ] **Step 1: Write the failing tests**

```python
def test_forwarded_header_ignored_when_no_trusted_proxy(rf, settings):
    settings.TRUSTED_PROXY_COUNT = 0
    req = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4")
    assert client_ip(req) == "10.0.0.1"
def test_one_trusted_proxy_uses_rightmost_entry(rf, settings):
    settings.TRUSTED_PROXY_COUNT = 1
    req = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="6.6.6.6, 1.2.3.4")
    assert client_ip(req) == "1.2.3.4"          # attacker-supplied 6.6.6.6 is ignored
def test_garbage_forwarded_header_falls_back_to_remote_addr(rf, settings):

def test_account_locks_after_five_failures(db, req):
    for _ in range(4): record_failure(req, "a@example.com")
    assert not is_blocked(req, "a@example.com")
    record_failure(req, "a@example.com")
    assert is_blocked(req, "a@example.com")
def test_account_lock_expires_after_15_minutes(db, req, time_machine):
def test_success_clears_account_counter(db, req):
def test_email_variants_share_one_counter(db, req):
    for e in ["A@example.com", " a@example.com", "a@EXAMPLE.com", "a@example.com", "A@Example.Com"]:
        record_failure(req, e)
    assert is_blocked(req, "a@example.com")
def test_unknown_email_locks_like_a_real_one(db, req):     # no enumeration via lockout
def test_ip_blocked_after_twenty_failures_across_accounts(db, rf):
    # 20 failures from 203.0.113.9 against 20 different emails → is_blocked(req, None) is True
    # a request from 203.0.113.10 is not blocked
def test_ip_block_lifts_when_failures_leave_the_window(db, rf, time_machine):
def test_rotating_forwarded_header_does_not_dodge_ip_block(db, rf, settings):   # TRUSTED_PROXY_COUNT = 0
def test_lockout_recorded_once_in_audit(db, req):
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_throttle.py -q`
- [ ] **Step 3: Implement**
  - `client_ip`: with a count of `n > 0`, take the `n`-th entry from the right of `X-Forwarded-For`; anything unparseable falls back to `REMOTE_ADDR`.
  - Per-account lockout uses django-axes: `AXES_FAILURE_LIMIT = 5`, `AXES_COOLOFF_TIME = timedelta(minutes=15)`, `AXES_LOCKOUT_PARAMETERS = ["username"]`, `AXES_CLIENT_IP_CALLABLE = "accounts.net.client_ip"`, axes backend first in `AUTHENTICATION_BACKENDS`, axes middleware installed. `throttle` is the only module that imports axes; it normalises the email before every call and drives axes through its handler so that code-step failures (Task 6) count too.
  - Per-IP blocking is our own: `IpFailure(ip, created)` rows, blocked when 20 or more fall inside the last 15 minutes. Rows older than a day are deleted opportunistically on write.
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit** — `git commit -m "feat: client address resolution and login throttling"`

---

### Task 5: Session states, login and deny-by-default

**Files:**
- Create: `backend/accounts/sessions.py`, `backend/api/{access,auth,schemas}.py`, `backend/api/routers/auth.py`, `backend/tests/test_login.py`, `backend/tests/test_deny_by_default.py`
- Modify: `backend/api/api.py`, `backend/tests/conftest.py`

**Interfaces:**
- Consumes: `throttle.*`, `audit.record`, `User`
- Produces:
  - `accounts.sessions.start_partial(request, user) -> None`
  - `accounts.sessions.partial_user(request) -> User | None` — `None` once 10 minutes have passed since `start_partial`, or if the user is inactive
  - `accounts.sessions.mark_second_factor_ok(request) -> None`
  - `accounts.sessions.next_step(request) -> Literal["login", "verify", "enrol", "change_password"] | None` — `None` means verified. Until Task 6 adds devices, a partial session always yields `"enrol"`.
  - `accounts.sessions.promote_if_ready(request) -> bool` — when the second factor is done and no password change is pending, calls Django's `login()` (rotating the session key) and returns True
  - `accounts.sessions.PARTIAL_LIFETIME = timedelta(minutes=10)`; settings `SESSION_COOKIE_AGE = 14 days`, `SESSION_SAVE_EVERY_REQUEST = True`, `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`
  - `api.auth.verified`, `api.auth.partial`, `api.auth.anonymous` — Ninja auth callables. `verified` is the API-wide default. All three enforce CSRF on unsafe methods. A failed check returns 401 `auth_required` with `details = {"session": "anonymous" | "partial", "next": <next_step>}`.
  - `api.access.ANONYMOUS: set[tuple[str, str]]` and `api.access.PARTIAL: set[tuple[str, str]]` — `(METHOD, path template)` pairs. Routers must use the matching auth callable and add their pair here.
  - Endpoints:
    - `GET /auth/session` (anonymous) → `{"state": "anonymous"|"partial"|"verified", "next": str|null, "user": {"id","email","is_instance_admin"}|null}`; sets the CSRF cookie
    - `POST /auth/login` (anonymous) `{email, password}` → 200 `{"next": "verify"|"enrol"}`; 401 `invalid_credentials`; 429 `locked`
    - `POST /auth/logout` (partial) → 204, flushes the session
  - Fixture `partial_client(user) -> api_client` logged in through the password step

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_login.py
def test_login_success_starts_partial_session(api_client, make_user):
    make_user("a@example.com")
    r = api_client.post("/auth/login", {"email": "A@Example.com ", "password": "correct horse battery"})
    assert r.status_code == 200 and r.json() == {"next": "enrol"}
    assert api_client.get("/auth/session").json()["state"] == "partial"
def test_wrong_password_and_unknown_email_are_indistinguishable(api_client, make_user):
    make_user("a@example.com")
    r1 = api_client.post("/auth/login", {"email": "a@example.com", "password": "wrong wrong wrong"})
    r2 = api_client.post("/auth/login", {"email": "nobody@example.com", "password": "wrong wrong wrong"})
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()
def test_unknown_email_still_runs_a_password_hash(api_client, mocker):   # hasher called once
def test_inactive_user_gets_invalid_credentials(api_client, make_user):
def test_sixth_attempt_is_429_locked_even_with_right_password(api_client, make_user):
def test_partial_session_expires_after_10_minutes(partial_client, time_machine):
    time_machine.shift(timedelta(minutes=10, seconds=1))
    assert partial_client.get("/auth/session").json()["state"] == "anonymous"
def test_logout_flushes_session(partial_client):
def test_post_without_csrf_token_is_403(make_user):   # Client(enforce_csrf_checks=True)
def test_login_success_and_failure_are_audited(api_client, make_user):

# tests/test_deny_by_default.py
def all_routes():   # every (METHOD, path) from api.get_openapi_schema()["paths"], path params filled with "1"
@pytest.mark.parametrize("method,path", all_routes())
def test_unlisted_route_refuses_anonymous(api_client, method, path):
    if (method, template_of(path)) in ANONYMOUS: pytest.skip()
    r = getattr(api_client, method.lower())(path)
    assert r.status_code == 401 and r.json()["error"]["details"]["session"] == "anonymous"
@pytest.mark.parametrize("method,path", all_routes())
def test_unlisted_route_refuses_partial(partial_client, method, path):
    if (method, template_of(path)) in ANONYMOUS | PARTIAL: pytest.skip()
    assert r.status_code == 401 and r.json()["error"]["details"]["session"] == "partial"
def test_access_lists_contain_no_stale_entries():      # every listed pair exists in the schema
def test_health_is_listed_anonymous():
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_login.py tests/test_deny_by_default.py -q`
- [ ] **Step 3: Implement.** Login checks `is_blocked` first, then authenticates; on an unknown email it hashes a dummy password so timing is comparable. The partial state lives in the session under one key holding `user_id`, `started` and `second_factor_ok`; Django's `login()` is called only by `promote_if_ready`.
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Commit** — `git commit -m "feat: session states, login, deny-by-default route guard"`

---

### Task 6: TOTP enrolment, verification and recovery codes

**Files:**
- Create: `backend/accounts/{totp,recovery}.py`, migration (`TotpDevice`, `RecoveryCode`, `UserSession`), `backend/tests/test_totp.py`
- Modify: `backend/accounts/{models,sessions}.py`, `backend/api/routers/auth.py`, `backend/api/access.py`, `backend/tests/conftest.py`

**Interfaces:**
- Consumes: `sessions.*`, `throttle.*`, `audit.record`, `Config.totp_encryption_key`
- Produces:
  - `TotpDevice`: `user` (FK), `secret_encrypted`, `confirmed: bool`, `last_step: int | None`; at most one confirmed and one unconfirmed per user
  - `RecoveryCode`: `user`, `code_hash`, `used_at`
  - `UserSession`: `user`, `session_key` (unique), `ip`, `user_agent`, `created`, `last_seen`
  - `accounts.totp.begin_enrolment(user) -> tuple[str, str]` — `(base32_secret, otpauth_uri)`; replaces any unconfirmed device
  - `accounts.totp.confirm_enrolment(user, code: str) -> bool` — confirms the pending device, deletes any previously confirmed one
  - `accounts.totp.verify(user, code: str) -> bool` — tolerance of one step either side; rejects any step `<= last_step`
  - `accounts.totp.has_confirmed_device(user) -> bool`
  - `accounts.totp.clear(user) -> None` — deletes devices and recovery codes
  - `accounts.recovery.generate(user) -> list[str]` — replaces existing codes; returns 10 codes formatted `xxxx-xxxx-xxxx-xxxx` from a 32-character lower-case alphabet
  - `accounts.recovery.redeem(user, code: str) -> bool`
  - `accounts.sessions.end_sessions(user, *, except_key: str | None = None) -> None`
  - `sessions.promote_if_ready` now also creates the `UserSession` row; `sessions.next_step` returns `"verify"` when the user has a confirmed device
  - Endpoints (all partial):
    - `POST /auth/enrol/start` → `{"secret", "otpauth_uri"}`; 409 `already_enrolled` if a confirmed device exists
    - `POST /auth/enrol/confirm` `{code}` → `{"recovery_codes": [10 strings], "next": "change_password"|null}`
    - `POST /auth/verify` `{code}` → `{"next": "change_password"|null}`; 401 `invalid_code`; 429 `locked`
    - `POST /auth/recovery` `{code}` → same as verify
  - Fixtures: `code_for(user) -> str` (current valid code), `enrolled(user) -> User` (confirmed device, created directly), `verified_client(user) -> api_client` (through the real login and verify endpoints)

- [ ] **Step 1: Write the failing tests**

```python
def test_secret_is_not_stored_in_plaintext(db, make_user):
    u = make_user(); secret, uri = begin_enrolment(u)
    raw = TotpDevice.objects.get(user=u).secret_encrypted
    assert secret not in str(raw) and uri.startswith("otpauth://totp/")
def test_enrolment_needs_a_valid_code(partial_client):       # wrong code → 401 invalid_code, device unconfirmed
def test_confirm_returns_ten_codes_once_and_verifies_session(partial_client, code_for_pending):
    r = partial_client.post("/auth/enrol/confirm", {"code": code})
    assert len(r.json()["recovery_codes"]) == 10 and r.json()["next"] is None
    assert partial_client.get("/auth/session").json()["state"] == "verified"
def test_recovery_codes_stored_hashed(db):                   # no returned code appears in any RecoveryCode field
def test_user_without_device_cannot_reach_verify(partial_client):   # 401, details.next == "enrol"
def test_session_key_rotates_on_promotion(...):
def test_accepted_code_cannot_be_replayed(db, enrolled_user, code_for):
    c = code_for(u); assert verify(u, c) is True; assert verify(u, c) is False
def test_adjacent_step_accepted_two_steps_away_rejected(db, time_machine):
@pytest.mark.parametrize("bad", ["", "abcdef", "12345", "1234567", "1" * 500, "١٢٣٤٥٦"])
def test_malformed_code_is_a_failure_not_an_error(partial_enrolled_client, bad):
    assert partial_enrolled_client.post("/auth/verify", {"code": bad}).status_code in (400, 401)
def test_code_with_spaces_and_leading_zero_accepted(...):    # "012 345" treated as "012345"
def test_recovery_code_works_once(...):                      # second use → 401; audit RECOVERY_CODE_USED
def test_recovery_code_accepts_upper_case_and_missing_dashes(...):
def test_five_bad_codes_lock_the_account(...):               # sixth → 429 locked, at verify and at recovery
def test_bad_password_and_bad_code_failures_add_up(...):     # 3 + 2 → locked
def test_full_verification_clears_failure_counter(...):
def test_end_sessions_keeps_only_the_excepted_key(...):
def test_verified_session_of_deactivated_user_is_refused(verified_client, user):
    user.is_active = False; user.save()
    assert verified_client.get("/auth/session").json()["state"] == "anonymous"
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_totp.py -q`
- [ ] **Step 3: Implement.** Use `django_otp.oath.TOTP` (30-second step, 6 digits) for the algorithm only; our own models hold the state. Secrets are 20 random bytes, encrypted with Fernet using the configured key. Codes are normalised by stripping spaces and dashes before any check. Recovery codes are hashed with SHA-256 after normalising to lower case without dashes (80 bits of entropy makes a slow hash unnecessary). `throttle.record_success` is called only when the session becomes verified. Extend `tests/test_deny_by_default.py` coverage by adding the four endpoints to `PARTIAL`.
- [ ] **Step 4: Run to verify they pass** — also rerun `tests/test_login.py tests/test_deny_by_default.py`.
- [ ] **Step 5: Commit** — `git commit -m "feat: enforced TOTP with recovery codes"`

---

### Task 7: Forced password change and account settings

**Files:**
- Create: `backend/api/routers/account.py`, `backend/tests/test_account.py`
- Modify: `backend/api/routers/auth.py`, `backend/api/access.py`, `backend/config/settings.py` (last-seen middleware), `backend/accounts/sessions.py`

**Interfaces:**
- Consumes: `validate_new_password`, `sessions.*`, `totp.*`, `recovery.*`, `audit.record`
- Produces:
  - `POST /auth/password/forced` (partial) `{new_password}` → `{"next": null}`; 401 with `details.next` if the second factor is not yet done; 409 `not_required` if `must_change_password` is false
  - `GET /account` → `{"id", "email", "is_instance_admin"}`
  - `POST /account/password` `{current_password, new_password}` → 204; 401 `invalid_credentials` on a wrong current password
  - `GET /account/sessions` → `[{"id", "ip", "user_agent", "created", "last_seen", "current": bool}]`
  - `DELETE /account/sessions/{id}` → 204; 404 for another user's session
  - `POST /account/2fa/reenrol/start` `{code}` (TOTP or recovery) → `{"secret", "otpauth_uri"}`
  - `POST /account/2fa/reenrol/confirm` `{code}` → `{"recovery_codes": [...]}`
  - `accounts.sessions.touch(request)` — middleware-called; updates `UserSession.last_seen` at most once a minute

- [ ] **Step 1: Write the failing tests**

```python
def test_forced_change_comes_after_second_factor(make_user, ...):
    # must_change user: login → next "verify"; verify → next "change_password"; state still "partial"
    # POST /auth/password/forced → state "verified", user.must_change_password False
def test_forced_change_refused_before_second_factor(...):    # 401, details.next == "verify"
def test_forced_change_applies_password_rules(...):          # 400 validation, details.password
def test_change_password_requires_current(verified_client):
def test_change_password_ends_other_sessions(make_user, ...):   # two verified clients; other one → anonymous
def test_new_password_same_as_old_rejected(...):
def test_sessions_list_marks_current(verified_client):
def test_revoke_other_session(...); def test_cannot_revoke_another_users_session(...):   # 404
def test_reenrol_requires_current_code(verified_client):     # wrong code → 401 invalid_code
def test_reenrol_replaces_device_and_recovery_codes(...):    # old code and old recovery codes stop working
def test_old_device_keeps_working_until_reenrol_confirmed(...):
def test_last_seen_updates_at_most_once_a_minute(...):
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_account.py -q`
- [ ] **Step 3: Implement.** Every password change records `PASSWORD_CHANGED` and calls `end_sessions(user, except_key=current)`. Re-enrolment failures count toward the account lockout.
- [ ] **Step 4: Run to verify they pass** — plus `tests/test_deny_by_default.py`.
- [ ] **Step 5: Commit** — `git commit -m "feat: forced password change and account settings"`

---

### Task 8: First-run setup

**Files:**
- Create: `backend/accounts/setup.py`, `backend/accounts/management/commands/bootstrap.py`, `backend/api/routers/setup.py`, migration (`SetupToken`), `backend/tests/test_setup.py`
- Modify: `backend/api/access.py`

**Interfaces:**
- Consumes: `Config.initial_admin_*`, `tokens` hashing rule, `throttle`, `sessions.start_partial`, `audit.record`
- Produces:
  - `accounts.setup.admin_exists() -> bool` — any user with `is_instance_admin`, active or not
  - `accounts.setup.bootstrap(config: Config, out: TextIO) -> Literal["exists", "env_admin", "token"]`
  - `manage.py bootstrap` — runs `migrate`, then `bootstrap`. On the token route it writes exactly one line `Setup token: <token>` to stdout.
  - `GET /setup/status` (anonymous) → `{"needs_setup": true}`; 404 once an admin exists
  - `POST /setup/admin` (anonymous) `{token, email, password}` → 201 `{"next": "enrol"}`, starts a partial session; 401 `invalid_token`; 404 once an admin exists

- [ ] **Step 1: Write the failing tests**

```python
def test_env_route_creates_admin_who_must_change_password(db, cfg):
    assert bootstrap(cfg(email="root@example.com", password="initial-password-1"), out) == "env_admin"
    u = User.objects.get(); assert u.is_instance_admin and u.must_change_password
    assert "Setup token" not in out.getvalue() and "initial-password-1" not in out.getvalue()
def test_env_route_needs_both_values(db, cfg):
    assert bootstrap(cfg(email="root@example.com", password=None), out) == "token"
def test_env_values_ignored_once_an_admin_exists(db, cfg, make_user):
    make_user("first@example.com", admin=True)
    assert bootstrap(cfg(email="root@example.com", password="initial-password-1"), out) == "exists"
    assert User.objects.count() == 1
def test_env_admin_not_recreated_after_password_change(db, cfg):   # run, change password, run again → unchanged
def test_weak_env_password_is_a_config_error(db, cfg):        # "short" → ConfigError, no user created
def test_token_route_prints_token_and_stores_only_hash(db, cfg):
    bootstrap(cfg(), out); token = re.search(r"^Setup token: (\S+)$", out.getvalue(), re.M)[1]
    assert token not in str(SetupToken.objects.values())
def test_restart_replaces_the_token(db, cfg, api_client):     # old token → 401 invalid_token
def test_setup_creates_admin_and_leads_to_enrolment(...):     # 201, next "enrol", SETUP_COMPLETED audited
def test_setup_endpoints_are_404_once_admin_exists(...):      # both endpoints, including with a valid old token
def test_inactive_admin_still_closes_setup(...):
def test_wrong_tokens_count_toward_ip_block(...):             # 20 bad tokens → 429
def test_two_simultaneous_setups_create_one_admin(transactional_db, ...):
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_setup.py -q`
- [ ] **Step 3: Implement.** `SetupToken` holds a single row. Creating the admin locks that row inside a transaction and deletes it on success, which serialises concurrent attempts.
- [ ] **Step 4: Run to verify they pass** — plus `tests/test_deny_by_default.py`.
- [ ] **Step 5: Commit** — `git commit -m "feat: first-run setup by env admin or setup token"`

---

### Task 9: Permissions and workspaces

**Files:**
- Create: `backend/permissions/{__init__,actions,core}.py`, `backend/workspaces/{__init__,apps,models,services}.py`, migration, `backend/api/routers/workspaces.py`, `backend/tests/{test_permissions,test_workspaces}.py`

**Interfaces:**
- Consumes: `User`, `audit.record`, `ApiError`
- Produces:
  - `workspaces.models.Role` (TextChoices): `OWNER="owner"`, `EDITOR="editor"`, `VIEWER="viewer"`
  - `Workspace`: `name` (1–100 characters after trimming), `created_by`, `created_at`, `deleted_at`
  - `Membership`: `user`, `workspace`, `role`; unique on `(user, workspace)`
  - `permissions.actions`: `INSTANCE_MANAGE_USERS="instance.manage_users"`, `INSTANCE_CREATE_INVITATION`, `INSTANCE_VIEW_AUDIT_LOG`, `WORKSPACE_CREATE`, `WORKSPACE_VIEW`, `WORKSPACE_RENAME`, `WORKSPACE_MANAGE_MEMBERS`, `WORKSPACE_INVITE`, `WORKSPACE_DELETE`, `WORKSPACE_RESTORE` (values follow the spec's table)
  - `permissions.core.INSTANCE` — sentinel target
  - `permissions.core.ROLE_ACTIONS: dict[Role, frozenset[str]]`
  - `permissions.core.can(user, action: str, target) -> bool` — `target` is `INSTANCE` or a `Workspace`
  - `permissions.core.require(user, action, target) -> None` — raises `ApiError(404, "not_found")` when the user cannot even view the workspace, otherwise `ApiError(403, "forbidden")`
  - `workspaces.services`: `create(user, name) -> Workspace`, `rename(ws, name)`, `soft_delete(ws)`, `restore(ws)`, `add_member(ws, user, role) -> Membership`, `change_role(ws, user, role)`, `remove_member(ws, user)`; rule violations raise `ApiError(409, code)` with codes `last_owner`, `already_member`, `restore_expired`. Each takes `actor` and `request` keyword arguments for the audit record.
  - `workspaces.services.RESTORE_WINDOW = timedelta(days=30)`
  - Endpoints: `GET /workspaces` (`?deleted=true` lists restorable ones the caller may restore), `POST /workspaces` `{name}`, `GET|PATCH|DELETE /workspaces/{id}`, `POST /workspaces/{id}/restore`, `GET /workspaces/{id}/members`, `POST /workspaces/{id}/members` `{email, role}` (404 `user_not_found` for an unknown email), `PATCH|DELETE /workspaces/{id}/members/{user_id}`
  - Workspace JSON: `{"id", "name", "role": str|null, "deleted_at": str|null}` — `role` is the caller's membership role, null for an admin who is not a member

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_permissions.py — the spec's table, exhaustively
EXPECTED = {  # action → roles allowed; "admin" is an instance admin with no membership
    WORKSPACE_VIEW: {"admin", "owner", "editor", "viewer"},
    WORKSPACE_RENAME: {"admin", "owner"}, WORKSPACE_MANAGE_MEMBERS: {"admin", "owner"},
    WORKSPACE_INVITE: {"admin", "owner"}, WORKSPACE_DELETE: {"admin", "owner"},
    WORKSPACE_RESTORE: {"admin", "owner"},
}
@pytest.mark.parametrize("action", EXPECTED)
@pytest.mark.parametrize("who", ["admin", "owner", "editor", "viewer", "outsider"])
def test_workspace_matrix(db, actors, ws, action, who):
    assert can(actors[who], action, ws) is (who in EXPECTED[action])
@pytest.mark.parametrize("action", [INSTANCE_MANAGE_USERS, INSTANCE_CREATE_INVITATION, INSTANCE_VIEW_AUDIT_LOG])
def test_instance_actions_are_admin_only(...):
def test_any_active_user_may_create_a_workspace(...): def test_inactive_user_can_do_nothing(...):
def test_unknown_action_raises_value_error(...):
def test_every_action_constant_is_covered_by_this_file():     # guards against an untested new action

# tests/test_workspaces.py
def test_creator_becomes_owner(verified_client): def test_name_trimmed_and_blank_rejected(...):
def test_list_shows_only_my_workspaces_admin_sees_all(...):
def test_outsider_gets_404_not_403(...): def test_viewer_rename_is_403(...):
def test_cannot_remove_or_demote_last_owner(...):             # 409 last_owner, including self-demotion
def test_owner_can_leave_when_another_owner_exists(...):
def test_concurrent_removal_of_last_two_owners_leaves_one(transactional_db):
    # two threads each remove a different owner; exactly one gets 409 and one owner remains
def test_add_member_by_email_variant(...):                    # " B@Example.com " finds b@example.com
def test_add_existing_member_is_409_already_member(...):
def test_delete_is_soft_and_hides_workspace(...):             # GET → 404; row still exists
def test_restore_within_30_days(...): def test_restore_after_30_days_is_409_restore_expired(..., time_machine):
def test_admin_who_is_not_a_member_can_manage_and_sees_role_null(...):
def test_membership_and_workspace_changes_are_audited(...):
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_permissions.py tests/test_workspaces.py -q`
- [ ] **Step 3: Implement.** Owner-count checks run inside a transaction that locks the workspace row with `select_for_update`. A soft-deleted workspace is invisible to every action except `WORKSPACE_RESTORE`.
- [ ] **Step 4: Run to verify they pass** — plus `tests/test_deny_by_default.py`.
- [ ] **Step 5: Commit** — `git commit -m "feat: permissions, workspaces and memberships"`

---

### Task 10: Invitations

**Files:**
- Create: `backend/accounts/tokens.py`, migration (`Invitation`), `backend/api/routers/invitations.py`, `backend/tests/test_invitations.py`
- Modify: `backend/accounts/models.py`, `backend/api/access.py`

**Interfaces:**
- Consumes: `permissions.require`, `workspaces.services.add_member`, `validate_new_password`, `sessions.start_partial`, `throttle`, `audit.record`
- Produces:
  - `accounts.tokens.new_token() -> tuple[str, str]` — `(token, sha256_hex)`; `accounts.tokens.hash_token(token: str) -> str`
  - `Invitation`: `token_hash`, `created_by`, `workspace` (null), `role` (null), `expires_at`, `used_at`, `used_by`, `revoked_at`; `INVITATION_LIFETIME = timedelta(days=7)`
  - `POST /invitations` `{workspace_id?: int, role?: str}` → 201 `{"id", "url", "expires_at"}` where `url` is `{PUBLIC_URL}/invite/{token}`. Without `workspace_id`: needs `INSTANCE_CREATE_INVITATION`. With it: needs `WORKSPACE_INVITE` and a `role`.
  - `GET /invitations` (`?workspace_id=`) → pending invitations the caller may manage, without tokens
  - `DELETE /invitations/{id}` → 204
  - `GET /invitations/token/{token}` (anonymous) → `{"workspace_name": str|null, "role": str|null}`
  - `POST /invitations/token/{token}/accept` (anonymous) `{email, password}` → 201 `{"next": "enrol"}`; 409 `email_taken`
  - Unknown, used, expired and revoked tokens all return the identical 404 `invalid_token`

- [ ] **Step 1: Write the failing tests**

```python
def test_admin_creates_instance_invitation(...): def test_owner_creates_workspace_invitation(...):
def test_editor_cannot_invite(...):                           # 403
def test_owner_cannot_create_instance_invitation(...):        # 403
def test_token_appears_only_in_create_response(...):          # not in GET list, not in DB, not in audit
def test_accept_creates_user_joins_workspace_and_requires_enrolment(...):
    # 201 next "enrol"; user has the invited role; state "partial"; cannot reach /workspaces yet (401)
def test_accept_normalises_email(...): def test_accept_applies_password_rules(...):
def test_accept_with_existing_email_is_409_and_leaves_invitation_unused(...):
@pytest.mark.parametrize("state", ["unknown", "used", "expired", "revoked"])
def test_dead_tokens_are_indistinguishable(state, ...):       # same status and body for inspect and accept
def test_invitation_expires_after_7_days(..., time_machine):
def test_two_simultaneous_accepts_create_one_user(transactional_db, ...):
def test_bad_tokens_count_toward_ip_block(...):
def test_invitation_to_deleted_workspace_is_invalid(...):
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_invitations.py -q`
- [ ] **Step 3: Implement.** Acceptance locks the invitation row, so a token is consumed exactly once.
- [ ] **Step 4: Run to verify they pass** — plus `tests/test_deny_by_default.py`.
- [ ] **Step 5: Commit** — `git commit -m "feat: invitations"`

---

### Task 11: Admin: users, recovery paths and audit view

**Files:**
- Create: `backend/accounts/services.py`, migration (`ResetLink`), `backend/accounts/management/commands/{reset_2fa,reset_password}.py`, `backend/api/routers/{admin_users,admin_audit}.py`, `backend/tests/{test_admin_users,test_recovery_paths,test_admin_audit}.py`
- Modify: `backend/api/routers/auth.py`, `backend/api/access.py`

**Interfaces:**
- Consumes: `permissions.require`, `tokens`, `totp.clear`, `sessions.end_sessions`, `validate_new_password`, `throttle.reset_account`, `audit`
- Produces:
  - `ResetLink`: `token_hash`, `user`, `created_by` (null when made by the command), `expires_at`, `used_at`; `RESET_LIFETIME = timedelta(hours=24)`
  - `accounts.services`: `deactivate(user, *, actor, request)`, `reactivate(...)`, `set_admin(user, value: bool, ...)`, `create_reset_link(user, *, actor, request) -> str` (URL `{PUBLIC_URL}/reset/{token}`), `reset_second_factor(user, *, actor, request)`. Rule violations raise `ApiError(409, "last_admin")`.
  - `GET /admin/users` → `[{"id", "email", "is_instance_admin", "is_active", "has_2fa", "created_at"}]`
  - `POST /admin/users/{id}/deactivate`, `POST /admin/users/{id}/reactivate` → 204
  - `PUT /admin/users/{id}/admin` `{is_instance_admin}` → 204
  - `POST /admin/users/{id}/reset-link` → 201 `{"url", "expires_at"}`
  - `POST /admin/users/{id}/reset-2fa` → 204
  - `GET /auth/reset/{token}` (anonymous) → 204 or 404 `invalid_token`; `POST /auth/reset/{token}` (anonymous) `{new_password}` → 204
  - `GET /admin/audit` `?event=&actor_id=&before=<id>&limit=` (default 50, max 200) → `{"items": [{"id", "time", "event", "actor_email", "target_type", "target_id", "ip", "details"}], "next_before": int|null}`, newest first
  - `manage.py reset_2fa <email>` and `manage.py reset_password <email>` (prints a reset URL); both exit non-zero with a message for an unknown email

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_admin_users.py
def test_non_admin_gets_403_on_every_admin_route(verified_client, ...):
def test_deactivate_ends_sessions_and_blocks_login(...):
def test_cannot_deactivate_or_demote_last_active_admin(...):  # 409 last_admin, including oneself
def test_inactive_admin_does_not_count_toward_last_admin(...):
def test_reactivate(...): def test_admin_flag_change_is_audited(...):

# tests/test_recovery_paths.py
def test_reset_link_sets_password_but_second_factor_still_required(...):
    # redeem → login with new password → next "verify"
def test_reset_link_single_use_and_expires_after_24_hours(..., time_machine):
def test_reset_ends_all_sessions_and_clears_must_change_and_lockout(...):
def test_dead_reset_tokens_indistinguishable(...):
def test_creating_a_second_link_invalidates_the_first(...):
def test_reset_2fa_forces_reenrolment_and_ends_sessions(...):   # next login → next "enrol"; old recovery codes dead
def test_reset_2fa_command(...): def test_reset_password_command_prints_working_url(...):
def test_commands_fail_for_unknown_email(...):

# tests/test_admin_audit.py
def test_filter_by_event_and_actor(...): def test_pagination_newest_first(...):
def test_limit_capped_at_200(...):
def test_no_secret_material_in_any_audit_row_after_full_flow(...):
    # run setup → enrol → invite → accept → reset; assert no password, code, token or secret
    # used in the flow appears in json.dumps of all AuditEvent.details
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_admin_users.py tests/test_recovery_paths.py tests/test_admin_audit.py -q`
- [ ] **Step 3: Implement.** Last-admin checks lock the admin rows in a transaction, as the last-owner check does.
- [ ] **Step 4: Run to verify they pass** — then the whole suite: `uv run pytest -q`.
- [ ] **Step 5: Commit** — `git commit -m "feat: admin user management, recovery paths, audit view"`

---

### Task 12: Frontend skeleton, API client and guards

**Files:**
- Create: `frontend/package.json`, `vite.config.ts`, `tsconfig.json`, `eslint.config.js`, `index.html`, `openapi.json`, `src/{main,App,routes}.tsx`, `src/constants.ts`, `src/api/{schema.d.ts,client.ts,hooks.ts}`, `src/auth/{SessionProvider,guards}.tsx`, `src/layout/Shell.tsx`, tests beside sources as `*.test.ts(x)`

**Interfaces:**
- Consumes: the API from Tasks 1–11
- Produces:
  - Scripts: `pnpm dev` (Vite, proxying `/api` to `localhost:8000`), `pnpm build`, `pnpm test` (Vitest), `pnpm lint`, `pnpm typecheck`, `pnpm gen:api` (exports the schema with `uv run --project ../backend python ../backend/manage.py export_openapi_schema --api api.api.api` into `openapi.json`, then runs `openapi-typescript` to `src/api/schema.d.ts`)
  - `api/client.ts`: `request<T>(method, path, body?) -> Promise<T>`; `class ApiFailure extends Error { status: number; code: string; details: Record<string, unknown> }`
  - `auth/SessionProvider.tsx`: `useSession() -> { state: "loading"|"anonymous"|"partial"|"verified", next: string|null, user: User|null, refresh(): Promise<void> }`
  - `auth/guards.tsx`: `<RequireVerified>`, `<RequirePartial step>`, `<RequireAdmin>`; `pathForStep(next: string|null) -> string` mapping `login→/login`, `verify→/verify`, `enrol→/enrol`, `change_password→/change-password`, `null→/`
  - Route paths: `/setup`, `/login`, `/verify`, `/enrol`, `/change-password`, `/invite/:token`, `/reset/:token`, `/` (workspace list), `/workspaces/:id`, `/account`, `/admin/users`, `/admin/invitations`, `/admin/audit`

- [ ] **Step 1: Write the failing tests**

```ts
// api/client.test.ts
it("sends the CSRF cookie value as X-CSRFToken on unsafe methods")
it("does not send X-CSRFToken on GET")
it("throws ApiFailure carrying status, code and details from the error body")
it("throws ApiFailure with code 'network' when the response is not JSON")
it("returns undefined for 204")
// auth/guards.test.tsx
it.each([["login","/login"],["verify","/verify"],["enrol","/enrol"],["change_password","/change-password"]])
  ("pathForStep(%s) is %s")
it("RequireVerified redirects an anonymous session to /login")
it("RequireVerified redirects a partial session to the step the server named")
it("RequireAdmin shows a not-permitted message to a non-admin")
it("a 401 from any request refreshes the session and redirects by details.next")
```

- [ ] **Step 2: Run to verify they fail** — `pnpm test`
- [ ] **Step 3: Implement.** Mantine for components, TanStack Query for server state, React Router for routing. `Shell` shows navigation, the signed-in email, admin links only for admins, and a sign-out button. Pages for the routes above are placeholders until Tasks 13 and 14.
- [ ] **Step 4: Run to verify they pass** — `pnpm test && pnpm lint && pnpm typecheck && pnpm build`
- [ ] **Step 5: Commit** — `git commit -m "feat: frontend skeleton, typed API client, route guards"`

---

### Task 13: Frontend authentication screens

**Files:**
- Create: `frontend/src/auth/{SetupPage,LoginPage,VerifyPage,EnrolPage,RecoveryCodes,ForcedPasswordPage,InvitationPage,ResetPage}.tsx` and a `.test.tsx` beside each
- Modify: `frontend/src/routes.tsx`

**Interfaces:**
- Consumes: `request`, `ApiFailure`, `useSession`, `pathForStep`; endpoints from Tasks 5–8, 10, 11
- Produces: the eight pages, each default-exported and mounted at its route from Task 12

- [ ] **Step 1: Write the failing tests**

```ts
// SetupPage: it("redirects to /login when /setup/status is 404")
//            it("submits token, email and password, then goes to /enrol")
// LoginPage: it("shows one generic message for invalid_credentials")
//            it("shows a wait message for 429 locked")
//            it("navigates by the returned next step")
// VerifyPage: it("has a switch to recovery-code entry that posts to /auth/recovery")
//             it("strips spaces from the code before sending")
// EnrolPage: it("renders the QR code and the secret as selectable text")
//            it("shows recovery codes after confirmation")
// RecoveryCodes: it("keeps Continue disabled until 'I have saved these' is ticked")
//                it("offers copy and download of the ten codes")
// ForcedPasswordPage, InvitationPage, ResetPage:
//            it("shows field errors from details.password under the password field")
//            it("requires the password to be typed twice and matching")
// InvitationPage: it("shows the workspace name and role when the invitation carries them")
//                 it("shows a single 'no longer valid' message for invalid_token")
```

- [ ] **Step 2: Run to verify they fail** — `pnpm test src/auth`
- [ ] **Step 3: Implement.** The QR code is rendered in the browser from `otpauth_uri` with `qrcode.react`. Recovery codes are held in component state only and are gone after navigation.
- [ ] **Step 4: Run to verify they pass** — `pnpm test && pnpm lint && pnpm typecheck`
- [ ] **Step 5: Commit** — `git commit -m "feat: authentication screens"`

---

### Task 14: Frontend workspaces, account and admin screens

**Files:**
- Create: `frontend/src/workspaces/{WorkspaceListPage,WorkspaceDetailPage,MembersTable}.tsx`, `frontend/src/account/AccountPage.tsx`, `frontend/src/admin/{UsersPage,InvitationsPage,AuditLogPage}.tsx`, tests beside each
- Modify: `frontend/src/routes.tsx`, `frontend/src/api/hooks.ts`

**Interfaces:**
- Consumes: endpoints from Tasks 7, 9, 10, 11; guards from Task 12

- [ ] **Step 1: Write the failing tests**

```ts
// WorkspaceListPage: it("lists workspaces and creates one by name")
//                    it("shows restorable deleted workspaces in a separate section")
// WorkspaceDetailPage: it("shows an empty bases panel with explanatory text")
//                      it("hides rename, delete and member controls from editors and viewers")
// MembersTable: it("shows the server's last_owner message when a role change is refused")
//               it("creates an invitation and shows its URL once with a copy button")
// AccountPage: it("lists sessions and marks the current one")
//              it("asks for a current code before starting re-enrolment")
// UsersPage: it("shows a generated reset link once with a copy button")
//            it("asks for confirmation before deactivating or resetting 2FA")
//            it("shows the server's last_admin message when refused")
// AuditLogPage: it("filters by event type and loads older entries with next_before")
```

- [ ] **Step 2: Run to verify they fail** — `pnpm test`
- [ ] **Step 3: Implement.** Destructive actions use a confirmation dialog. Controls are hidden by the `role` and `is_instance_admin` values the API returns; the server remains the authority.
- [ ] **Step 4: Run to verify they pass** — `pnpm test && pnpm lint && pnpm typecheck && pnpm build`
- [ ] **Step 5: Commit** — `git commit -m "feat: workspace, account and admin screens"`

---

### Task 15: Container, static serving and documentation

**Files:**
- Create: `docker/Dockerfile`, `docker/entrypoint.sh`, `docker-compose.yml`, `README.md`, `backend/config/spa.py`, `backend/tests/test_spa.py`
- Modify: `backend/config/{settings,urls}.py`

**Interfaces:**
- Consumes: `manage.py bootstrap`, `pnpm build` output in `frontend/dist`
- Produces:
  - Setting `FRONTEND_DIST: Path` (default `/app/frontend_dist`, overridable in tests)
  - Any path not under `/api/` or matching a built asset returns `index.html`
  - `docker compose up` starts `postgres` (named volume, healthcheck) and `app` (port 8000, healthcheck on `/api/v1/health`, depends on a healthy postgres)
  - `entrypoint.sh`: `python manage.py bootstrap` then `uvicorn config.asgi:application --host 0.0.0.0 --port 8000`

- [ ] **Step 1: Write the failing tests**

```python
def test_spa_route_serves_index(client, settings, tmp_path):   # dist with index.html → GET /login is 200 HTML
def test_api_404_is_json_not_index(client, ...):               # GET /api/v1/nope → JSON not_found
def test_index_is_not_cached_but_hashed_assets_are(...):       # Cache-Control: no-cache vs immutable
def test_missing_dist_gives_clear_503(client, settings):       # not a stack trace
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_spa.py -q`
- [ ] **Step 3: Implement.** Multi-stage Dockerfile: a Node stage runs `pnpm install --frozen-lockfile && pnpm build`; the final stage uses a uv base image, `uv sync --frozen --no-dev`, copies the built frontend, runs as a non-root user, and sets `DJANGO_SETTINGS_MODULE=config.settings`. README covers: what the project is, quick start (`cp .env.example .env`, generate the three secrets, `docker compose up`), both first-run routes and where the setup token appears (`docker compose logs app`), the `TRUSTED_PROXY_COUNT` setting with a Tailscale Funnel example, the three recovery paths and their commands, and local development.
- [ ] **Step 4: Verify**
  - `uv run pytest -q` → pass
  - `docker compose up --build -d`, then `curl -s localhost:8000/api/v1/health` → `{"status": "ok"}`, and `docker compose logs app | grep "Setup token:"` → one line
  - With `SECRET_KEY=change-me` in `.env`: the app container exits and its log names `SECRET_KEY`
- [ ] **Step 5: Commit** — `git commit -m "feat: container image, compose stack, README"`

---

### Task 16: End-to-end tests and CI

**Files:**
- Create: `scripts/e2e-server.sh`, `frontend/playwright.config.ts`, `frontend/e2e/{helpers.ts,setup.spec.ts,invitation.spec.ts,recovery.spec.ts}`, `.github/workflows/ci.yml`
- Modify: `frontend/package.json` (`e2e` script; dev dependency `otpauth`)

**Interfaces:**
- Consumes: the whole stack
- Produces:
  - `scripts/e2e-server.sh`: recreates database `e2e` on the dev Postgres, builds the frontend, runs `manage.py bootstrap` with stdout saved to `frontend/e2e/.bootstrap.log`, then serves on port 8010 with `PUBLIC_URL=http://localhost:8010`
  - `e2e/helpers.ts`: `setupToken() -> string` (reads the log), `totp(secret: string) -> string`, `createAdmin(page) -> { email, password, secret }`
  - CI jobs: `backend` (Postgres 16 service; `uv sync --frozen`; `ruff check`; `ruff format --check`; `ty check`; `pytest`), `frontend` (`pnpm install --frozen-lockfile`; lint; typecheck; test; build), `api-types` (`pnpm gen:api` then `git diff --exit-code`), `e2e` (Playwright, Chromium only), `image` (`docker build`)

- [ ] **Step 1: Write the end-to-end tests**

```ts
// setup.spec.ts
test("first run: token → admin → enrol → recovery codes → workspace list", ...)
test("setup page is gone after the admin exists", ...)
test("sign out, sign in with password and TOTP", ...)
test("a wrong code shows an error and a recovery code signs in once", ...)
// invitation.spec.ts
test("owner invites a viewer; viewer joins, enrols, sees the workspace, has no member controls", ...)
test("a used invitation link shows the no-longer-valid message", ...)
// recovery.spec.ts
test("admin creates a reset link; user sets a new password and still needs TOTP", ...)
test("admin resets a user's 2FA; user must enrol again at next login", ...)
```

- [ ] **Step 2: Run them** — `pnpm e2e` → all pass. A failure here is a defect in an earlier task: fix it there, with a unit test that reproduces it.
- [ ] **Step 3: Write `ci.yml`** with the five jobs, triggered on push and pull request.
- [ ] **Step 4: Verify** — run each job's commands locally in order; all exit 0. Confirm `pnpm gen:api` leaves the working tree clean.
- [ ] **Step 5: Commit** — `git commit -m "test: end-to-end flows and CI"`

---

## Spec coverage

| Spec section | Tasks |
|---|---|
| 3 Architecture, tooling | 1, 12, 15, 16 |
| 4 Session states, login | 5 |
| 4 TOTP, recovery codes | 6, 7 |
| 4 Passwords | 2, 7 |
| 4 Brute-force protection | 4, 5, 6 |
| 4 Responses that do not leak | 5, 10, 11 |
| 4 Sessions | 5, 6, 7 |
| 4 Joining and recovery | 10, 11 |
| 5 First-run setup | 8 |
| 6 Workspaces, roles, permission function | 9 |
| 7 Audit log | 3, 11 |
| 8 Configuration | 1 |
| 9 API | 5–11 |
| 10 Frontend | 12, 13, 14 |
| 11 Testing | every task, 16 |
| 12 Done when | 15, 16 |
