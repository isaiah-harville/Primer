# Retrieval

Retrieval is the only process that touches a vector store. Nothing else
names a collection, a table, or a filter syntax.

## The scope filter

Every read and every delete carries a filter built in one place, from the
request's library and generations. It is never assembled at a call site.

Isolation that depends on each caller remembering to add a condition holds
right up until the first caller forgets.

Scope is required and has no default. A request that could omit its library
is refused before any store is reached, because on the day someone forgot,
an empty filter would return another user's documents.

## The principal is audit context

Requests carry the acting principal, but Retrieval does not use it to decide
access. Whether that caller may read that library was decided by Control
before the request was made; re-deciding it here, without Control's data,
would be guessing.

## Generations

A **generation** is one build of one document version's index.

<div class="primer-diagram" markdown>
![Index generations](../assets/diagrams/generations.svg#only-light)
![Index generations](../assets/diagrams/generations-dark.svg#only-dark)
</div>

Searches read only the generation Control marks active, so a rebuild in
progress is invisible rather than partially answering questions. Activation
is a single row update, so every answer changes at the same instant.

A build that is short of the passages it should hold never activates.
Activating it would drop the missing passages from every future answer, with
nothing to show that anything was lost — so the index stage's whole job is
to count, compare, and refuse.

## Cleanup

Retiring a superseded build and erasing a deleted document are the same
operation with one parameter different, so they share a code path rather
than two that must stay in agreement about what "gone" means.

Cleanup addresses a *version* rather than a generation, because the builds a
version has been through are not recorded anywhere and the point of cleanup
is to leave nothing behind.

Superseded generations are retired **after** activation, never before. Until
Control has switched, the older generation is what searches are reading.

## No Primer vector adapter

Haystack's `DocumentStore` protocol is already that abstraction. Wrapping it
would add a layer whose only purpose would be to become a second place for
isolation bugs to live.

## The conformance suite

pgvector and Qdrant are both supported, so both run the same tests: write,
filtered search, cross-library and cross-owner isolation, duplicate
indexing, pending-generation invisibility, generation swap, delete, repeated
delete, dimension mismatch, and citation round-trip.

The isolation cases put the *same words* in two libraries, so nothing but
the filter separates them. A backend that ignored it fails there rather than
in production.

That suite has already earned its place: it caught the pgvector integration
naming its indexes with fixed defaults, which makes two Primer tables in one
schema collide on creation.
