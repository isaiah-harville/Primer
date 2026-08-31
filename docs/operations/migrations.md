# Migrations

Primer never runs migrations at startup. Applying them is an explicit step,
so a rolling deployment cannot have several instances racing to alter the
same schema.

## Applying them

```bash
cd services/control-api
PRIMER_DATABASE_URL=postgresql://user:pass@host/primer uv run alembic upgrade head
```

The URL comes from the environment, never from a file in the repository, so
no deployment's credentials live in version control.

## Checking where you are

```bash
PRIMER_DATABASE_URL=... uv run alembic current
PRIMER_DATABASE_URL=... uv run alembic history
```

## Rolling back

Every migration has a tested downgrade, verified by a round trip against a
real PostgreSQL in CI. A migration that cannot be rolled back cannot be
safely deployed.

```bash
PRIMER_DATABASE_URL=... uv run alembic downgrade -1
```

Downgrades do not drop the `control` schema itself, because it holds
Alembic's own version table.

## Schema layout

Control's tables live in a dedicated `control` schema, and Retrieval's
vectors in their own. Neither service's migrations touch the other's tables,
so they can share one PostgreSQL instance without coordinating releases.

## Drift

CI asserts that the migrations and the models describe the same schema. A
model changed without a migration fails the build rather than surfacing in
production as a query against a column that was never created.
