# TODOs

Deliberately deferred work, with what triggers it.

## Store local secrets outside plain-text `.env`

`apps/api/.env` holds the login password hash and the JWT signing secret in plain text.
It is git-ignored, has never been committed, and is `chmod 600`. That is acceptable
for local development today. The JWT secret is the sensitive value: anyone holding it
can create sessions without the password.

Options when this is picked up:

- **1Password CLI:** `.env` keeps only `op://...` references, and the app is started
  with `op run --env-file=apps/api/.env -- ...`, so secrets are never on disk.
- **macOS Keychain:** store values with `security add-generic-password` and export
  them in a small start script.

Production is separate and already planned for Phase 1b: SSM Parameter Store
SecureString, readable only by the API task's IAM role, with production values that
are never reused locally.

## Eager-load relationships on `GET /matches` and `GET /casting-calls`

Relationship access (`saved_matches -> role -> casting_call`, `casting_call -> roles`)
is lazy, so these endpoints issue N+1 queries. Add `selectinload`/`joinedload` to
each query when the dashboard is visibly slow.

## Cross-source dedup

When Backstage and Casting Networks both list the same project, it is stored as two
separate `casting_calls` rows. There is no shared id across sources, so this likely
needs a title + location + date similarity heuristic. The same applies within Casting
Networks: a project that appears in two daily digests is stored once per email.
