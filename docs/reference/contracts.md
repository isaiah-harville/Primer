# Contracts

The wire types shared between Primer's services. They are strict by default:
unknown fields are rejected rather than ignored, and every model is
immutable once constructed.

That strictness is the point. A field silently dropped between two services
is a bug that surfaces as missing data much later, somewhere else.

The web app does not restate them. Each service's OpenAPI schema is written
to `schemas/` by `scripts/dump_openapi.py`, and the TypeScript types are
generated from those files into `apps/web/src/lib/api/generated/`. Both are
checked in, and CI regenerates and diffs both — so a field renamed here is a
failed build rather than a runtime surprise in a browser.

```bash
uv run python scripts/dump_openapi.py   # contracts -> schemas/
pnpm run generate:api                   # schemas/ -> TypeScript
```

What is *not* generated is the part that decides who a request is from: the
identity headers this server forwards to Primer are hand-written and
reviewed, in `apps/web/src/lib/server/`. A tool emitting that from a
document describing something else is not a saving worth making.

## Identity

::: primer_contracts.identity

## Errors

::: primer_contracts.errors

## Libraries

::: primer_contracts.libraries

## Documents

::: primer_contracts.documents

## Chunks

::: primer_contracts.chunks

## Retrieval

::: primer_contracts.retrieval

## Ingestion jobs

::: primer_contracts.ingestion

## Indexing

::: primer_contracts.indexing
