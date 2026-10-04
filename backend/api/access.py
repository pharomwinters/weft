"""Routes reachable without a verified session.

Every other route requires one (api.auth.verified is the API-wide default).
Entries are (METHOD, path template relative to /api/v1) and each needs a
reason in the commit message that adds it.
"""

ANONYMOUS: set[tuple[str, str]] = {
    ("GET", "/health"),  # liveness probe
    ("GET", "/auth/session"),  # the SPA asks who it is before anything else
    ("POST", "/auth/login"),  # the password step
    # First-run setup happens before any account exists; both are 404 afterwards.
    ("GET", "/setup/status"),
    ("POST", "/setup/admin"),
    # The invitee has no account yet; the token is the credential.
    ("GET", "/invitations/token/{token}"),
    ("POST", "/invitations/token/{token}/accept"),
    # A forgotten password means no session; the reset token is the credential.
    ("GET", "/auth/reset/{token}"),
    ("POST", "/auth/reset/{token}"),
}

PARTIAL: set[tuple[str, str]] = {
    ("POST", "/auth/logout"),  # lets a half-logged-in user abandon the attempt
    # The second-factor step is what turns a partial session into a verified one.
    ("POST", "/auth/enrol/start"),
    ("POST", "/auth/enrol/confirm"),
    ("POST", "/auth/verify"),
    ("POST", "/auth/recovery"),
    # Due after the second factor and before the session can become verified.
    ("POST", "/auth/password/forced"),
}
