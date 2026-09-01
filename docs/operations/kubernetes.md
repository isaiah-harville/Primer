# Kubernetes

This is the multi-user deployment. Compose is deliberately single-user; here
is where the ingress, the identity provider, and the trusted-header boundary
live.

```bash
helm install primer deploy/helm/primer \
  --set ingress.host=primer.example.com \
  --set postgresql.existingSecret=primer-postgres \
  --set rabbitmq.existingSecret=primer-rabbitmq \
  --set auth.oidc.issuerUrl=https://auth.example.com/application/o/primer/ \
  --set auth.oidc.clientId=primer \
  --set auth.oidc.existingSecret=primer-oidc \
  --set inference.chat.baseUrl=http://vllm.ai.svc:8000/v1 \
  --set inference.chat.model=llama-3.1-8b-instruct \
  --set inference.embeddings.baseUrl=http://vllm.ai.svc:8000/v1 \
  --set inference.embeddings.model=bge-large-en-v1.5 \
  --set inference.embeddings.dimensions=1024
```

## Installing from the registry

Each push to `main` publishes the chart to GHCR, so an install does not need
a checkout:

```bash
helm install primer oci://ghcr.io/isaiah-harville/charts/primer \
  --version 0.1.0 \
  --set ingress.host=primer.example.com \
  ...
```

Publishing happens only from `main`. A chart pushed from a pull request
would let anyone who can open one publish under this repository's name.

## Secrets you provide

The chart creates exactly one secret and references the rest. A chart that
generated database passwords would put them in the release, in `helm get
values`, and in whatever stores your release history.

| Secret | Keys |
| --- | --- |
| `postgresql.existingSecret` | `database-url` |
| `rabbitmq.existingSecret` | `broker-url` |
| `auth.oidc.existingSecret` | `client-secret`, `cookie-secret` |
| `inference.*.existingSecret` | API keys, if your endpoint needs them |

The one it does create is Primer's own cluster-internal service token, which
means nothing outside the release. It is generated once and preserved across
upgrades — regenerating it on every `helm upgrade` would leave in-flight
workers holding a credential the API had just stopped accepting.

## How identity works

Primer never validates a token. `oauth2-proxy` verifies the user against
your provider and injects headers naming them, which Primer trusts.

That trust is why two things in this chart matter more than anything else:

**Every service is `ClusterIP`.** Nothing is exposed outside the cluster.
Anything that could reach the Control API directly could set the identity
headers itself and be any user.

**The ingress strips inbound identity headers.** A request arriving with its
own `X-Auth-Request-User` has it removed before it reaches the proxy. Both
are asserted by tests that render the chart and read the result.

!!! danger "If you replace the ingress, keep the header stripping"
    A different ingress controller needs the same rule expressed its own
    way. Without it, anyone who can reach the ingress is any user they care
    to name — and nothing about the deployment will look wrong.

Setting `auth.mode=disabled` removes the proxy entirely rather than putting
it in a permissive mode, so there is no half-configured edge that looks like
it is authenticating.

## Migrations

Run as a `pre-install,pre-upgrade` hook, once per release. An init container
would run once per pod, so a three-replica rollout would have three
processes racing to alter the same schema.

A failed migration fails the release before any new pod starts.

## Scale

**Parsing and indexing are separate deployments.** Parsing is CPU-heavy and
holds whole documents in memory; embedding and indexing mostly wait on a
network call. Splitting them by queue lets each scale on what constrains it,
and stops a burst of uploads starving the stage that finishes them.

**The parse worker keeps a model cache.** Docling downloads its layout
models on first use, and without a persistent volume every pod restart
re-downloads about half a gigabyte from a third-party host.

**Source storage must be shared.** More than one replica means object
storage: a `ReadWriteOnce` volume cannot be mounted across nodes.

## What is not here

No PostgreSQL, RabbitMQ, or model server. A chart that shipped its own
database is one people run in production by accident, and Primer's whole
premise is that you already have the infrastructure you want to keep your
documents on.
