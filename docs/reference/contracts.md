# Contracts

The wire types shared between Primer's services. They are strict by default:
unknown fields are rejected rather than ignored, and every model is
immutable once constructed.

That strictness is the point. A field silently dropped between two services
is a bug that surfaces as missing data much later, somewhere else.

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
