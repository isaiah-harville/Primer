# Configuration

Every setting is an environment variable prefixed `PRIMER_`. Unknown
settings are rejected at startup rather than ignored, so a typo fails loudly
instead of silently keeping a default.

## Control API

| Variable | Default | Notes |
| --- | --- | --- |
| `PRIMER_AUTH_MODE` | `disabled` | `disabled` or `oidc` |
| `PRIMER_DATABASE_URL` | local PostgreSQL | Migrations are applied out of band |
| `PRIMER_SOURCE_STORE_URL` | `file:///var/lib/primer/sources` | Any fsspec URL |
| `PRIMER_MAX_UPLOAD_BYTES` | `104857600` | Enforced while reading |
| `PRIMER_BROKER_URL` | unset | Unset leaves uploads queued |
| `PRIMER_INTERNAL_API_TOKEN` | unset | **Unset denies the internal API** |
| `PRIMER_SUBJECT_HEADER` | `X-Auth-Request-User` | Set by the proxy |
| `PRIMER_JOB_LEASE_SECONDS` | `300` | Before another worker may re-claim |
| `PRIMER_MAX_JOB_ATTEMPTS` | `5` | Hard bound, independent of workers |

## Ingestion workers

| Variable | Default | Notes |
| --- | --- | --- |
| `PRIMER_BROKER_URL` | local RabbitMQ | Must match Control's |
| `PRIMER_CONTROL_URL` | `http://control-api:8000` | Cluster-internal |
| `PRIMER_RETRIEVAL_URL` | `http://retrieval:8000` | Cluster-internal |
| `PRIMER_SERVICE_TOKEN` | unset | Must match the services' tokens |
| `PRIMER_SOURCE_STORE_URL` | `file:///var/lib/primer/sources` | Same store as Control |
| `PRIMER_ENABLE_OCR` | `true` | Read text from images |
| `PRIMER_CHUNK_TOKENIZER` | unset | Tokenizer of the embedding model |
| `PRIMER_MAX_CHUNK_TOKENS` | `512` | Ignored without a tokenizer |
| `PRIMER_MAX_CHUNKS_PER_DOCUMENT` | `5000` | Refuse rather than half-index |
| `PRIMER_PARSE_DEADLINE_SECONDS` | `900` | Checked between phases |
| `PRIMER_MAX_RETRIES` | `4` | Control holds its own bound |

## Retrieval

| Variable | Default | Notes |
| --- | --- | --- |
| `PRIMER_VECTOR_STORE` | `pgvector` | `pgvector` or `qdrant` |
| `PRIMER_DATABASE_URL` | local PostgreSQL | For pgvector |
| `PRIMER_VECTOR_SCHEMA` | `vectors` | Kept apart from Control's schema |
| `PRIMER_QDRANT_URL` | unset | **Required** when using Qdrant |
| `PRIMER_EMBEDDING_MODEL` | `text-embedding-3-small` | |
| `PRIMER_EMBEDDING_DIMENSIONS` | `1536` | Must match the model |
| `PRIMER_EMBEDDING_BASE_URL` | unset | Any OpenAI-compatible endpoint |
| `PRIMER_EMBEDDING_API_KEY` | unset | |
| `PRIMER_INTERNAL_API_TOKEN` | unset | **Unset denies the internal API** |

## Settings that fail at startup

Some combinations are refused rather than accepted and worked around later:

- `PRIMER_AUTH_MODE=oidc` with an empty subject header. The alternative is a
  deployment that believes it is authenticated but authenticates nobody.
- `PRIMER_VECTOR_STORE=qdrant` with no `PRIMER_QDRANT_URL`. Discovering that
  on the first search means it surfaces as a broken product rather than a
  broken deployment.

## Changing the embedding model

Changing the model or its dimensions invalidates every existing vector.
Vectors from different models are not comparable, and a store will reject
the wrong width outright.

Reindex your documents after such a change. Primer does not yet do this for
you, and will not detect it on your behalf.
