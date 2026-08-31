# Deploying

## What you need

| Component | Required | Notes |
| --- | --- | --- |
| PostgreSQL | yes | With `pgvector` if using it as the vector store |
| Object storage | yes | A directory is fine for a single node |
| RabbitMQ | for ingestion | Without it, uploads stay `queued` |
| Embedding endpoint | for retrieval | Any OpenAI-compatible API |
| `oauth2-proxy` | for multi-user | Not needed with auth off |
| Qdrant | optional | Alternative to pgvector |

## The processes

```bash
# Control API
uv run --package primer-control uvicorn primer_control.app:create_app --factory

# Ingestion workers
uv run --package primer-ingestion celery -A primer_ingestion.worker worker \
  -Q ingestion.parse,ingestion.embed,ingestion.index,ingestion.delete

# Retrieval
uv run --package primer-retrieval uvicorn primer_retrieval.app:create_app --factory
```

Workers can be split by queue. Parsing is CPU-heavy and holds whole
documents in memory; embedding is mostly waiting on a network call. Running
them as separate deployments lets each scale on what actually constrains it.

## Order of operations

1. Create the database and run [migrations](migrations.md).
2. Start Retrieval, so workers have somewhere to send passages.
3. Start Control.
4. Start workers.

Starting out of order is not harmful — jobs wait, and stages retry — but
documents will sit in `queued` until the chain is complete.

## Putting it behind the proxy

Primer trusts the identity headers it receives.

!!! danger "Bind so that only the proxy can reach Control"
    If the Control API is reachable directly, anyone who can reach it can
    set the identity headers themselves and act as any user. This is the
    single most important thing to get right in a shared deployment.

The proxy must also not route `/internal` from outside. Those endpoints are
guarded by a service credential, but they are not meant to be exposed.

## Health checks

Both services expose `/health/live`. Control also exposes `/health/ready`,
which reports unready when it cannot reach PostgreSQL.

Use liveness for restarts and readiness for load-balancer membership: a
Control instance that cannot reach its database should stop receiving
traffic without being killed and restarted in a loop.

## Scaling

Every service is stateless and can run several replicas. The design assumes
it:

- Two workers handed the same message cannot both do the work; the loser is
  told the stage is already claimed.
- A worker that dies mid-stage has its lease expire, and another picks the
  job up.
- Concurrent uploads of identical bytes converge on one stored object.
