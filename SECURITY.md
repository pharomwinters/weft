# Security policy

Weft is meant to be safe to expose to the open internet, so security reports
are taken seriously and are very welcome.

## Reporting a vulnerability

**Please do not open a public issue or pull request for a security problem.**

Email **asgardehs@proton.me** with:

- what the problem is and what an attacker could do with it;
- the steps, request or code needed to reproduce it;
- the version or commit you tested, and anything unusual about your setup
  (reverse proxy, `TRUSTED_PROXY_COUNT`, and so on).

If you are not sure whether something counts, send it anyway.

You will get a reply acknowledging the report. Please give the fix time to be
released before you publish details; you will be credited in the release
notes unless you would rather not be.

## Supported versions

Weft has not made a tagged release yet. Until it does, fixes land on the
`main` branch only, so please test against the latest `main`.

## What is in scope

Anything that weakens the guarantees the project makes, for example:

- reaching data or an API endpoint without a fully verified (two-factor)
  session;
- bypassing or weakening two-factor authentication, recovery codes, account
  lockout or the per-address login limit;
- acting outside your role in a workspace, or as an instance admin when you
  are not one;
- creating an admin by any route other than first-run setup;
- recovering or reusing invitation, password-reset or setup tokens;
- secrets (passwords, TOTP secrets, recovery codes, tokens) appearing in
  logs, the audit log or API responses.

## Known and accepted

These are deliberate trade-offs, described in the design spec, rather than
vulnerabilities:

- Someone who knows an email address can keep that account locked for 15
  minutes at a time by failing to sign in. The lockout is short and audited.
- With `TRUSTED_PROXY_COUNT` set higher than the real number of proxies, a
  client can forge the address used for the per-address limit. Set it to the
  real number.
