# Identity and access

Primer never validates a token, and has no password database.

<div class="primer-diagram" markdown>
![Identity and authorization](../assets/diagrams/authorization.svg#only-light)
![Identity and authorization](../assets/diagrams/authorization-dark.svg#only-dark)
</div>

## Where identity comes from

An authenticating proxy — `oauth2-proxy` or equivalent — verifies the user
against your identity provider and injects headers naming them. Primer
derives a stable internal user id from the subject in those headers.

This is why Primer supports any OIDC provider without integrating with any
of them: the part that differs between providers happens before the request
arrives.

!!! danger "The headers are trusted, so the network must enforce them"
    Primer believes its identity headers. If the app is reachable without
    going through the proxy, anyone can set those headers and become anyone.
    Bind it so that only the proxy can reach it.

## Turning authentication off

With authentication disabled, every request is one fixed local user and the
identity headers are ignored entirely — not merely defaulted. A single-user
laptop install needs no proxy; anything shared does.

## Authorization is a predicate

Access is not a check that runs before a query. It *is* part of the query: a
SQL expression that gets composed into it.

Listing libraries and fetching one apply the same expression, so there is no
second code path to drift. When shared libraries arrive, they become one
more clause in one place, rather than a change to every route.

## 404, never 403

Anything you may not see reports "not found" — including things that
certainly exist.

A 403 would confirm that a particular library or document exists, which is
itself a disclosure. The tests assert that a forbidden document and a
nonexistent one are indistinguishable on every route, including download.

## Service credentials

Workers and Retrieval talk to each other on cluster-internal APIs guarded by
a shared service credential, separate from user identity. Those routes act
on jobs, not on behalf of a person.

An unset credential denies every request. Treating "none configured" as
"none required" would turn a missing environment variable into an open
internal API.
