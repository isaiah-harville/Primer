# Ingestion

Turning an uploaded file into searchable passages takes minutes, can fail
halfway, and must never run twice. The design is shaped almost entirely by
those three facts.

<div class="primer-diagram" markdown>
![Ingestion pipeline states](../assets/diagrams/ingestion-pipeline.svg#only-light)
![Ingestion pipeline states](../assets/diagrams/ingestion-pipeline-dark.svg#only-dark)
</div>

## Messages carry a job id and nothing else

Everything a worker needs arrives when it claims the job. A message that sat
in a queue while the document was replaced therefore cannot act on a stale
copy of what it was published with.

## Stages, entry states, and leases

Each stage names three states: the one it must be claimed from, the one its
holder sets while working, and the one completion advances to — which is the
next stage's entry state. A redelivered message finds the job past its
stage's entry state and is told the stage is already done.

A claim is held by a **lease**, not by the state alone. State alone cannot
exclude a second worker: one that crashed mid-stage leaves the job marked
active, and a rule that refused to re-enter an active stage would strand it
forever. The lease expires instead, and the stage becomes claimable again
with no operator involved.

Every transition is a single conditional update. Read-then-write would let
two workers both observe a claimable job and both proceed.

## Publishing happens after the commit

An upload is committed before its message is published. A message sent
first could outlive a rolled-back upload, leaving a worker to claim a job
that does not exist.

The opposite failure is possible and is the one worth having: a crash
between committing and publishing leaves a job queued with no message. That
is visible, re-enqueueable, and harms nothing meanwhile.

## Retries

A worker reports whether a failure was transient, because it is the only
party that knows. Transient failures release the lease and return the job to
its stage's entry state; a document Primer cannot read fails terminally
without consuming the retry budget.

Control holds the hard attempt bound rather than trusting a worker's own
counter, which a broker redelivery resets. Backoff is jittered, so a broker
outage does not return as a synchronised herd of retries.

Messages the broker gives up on go to a dead-letter queue, where an operator
can find them. Dropping them would leave a document stuck with nothing to
explain why.

## Parsing

Conversion and chunking are [Docling](https://docling-project.github.io/docling/).
Primer adds no parser and no splitter of its own.

Conversion is the first code to touch bytes a stranger uploaded, so it runs
against a private, read-only copy in a directory that is removed on every
path out.

Its time budget is checked between phases rather than by interrupting the
converter: that work happens inside native extensions, where killing a
thread risks a corrupt process. The hard stop is the worker's task time
limit, which kills the process and lets the job's lease expire.

## Chunks carry their scope

Every passage carries its library, document, version, owner, and generation.
Retrieval authorizes by filtering on those fields, and a filter cannot
consult a database.

Chunk ids are derived from the version, the generation, and the position, so
re-running a stage rewrites the same rows rather than doubling the index.

Each passage keeps two texts: the document's own words, which is what a
citation quotes, and a version with its section heading prepended, which is
what gets embedded. A heading helps a passage keep the subject it is about;
putting it in the citation would quote words the document does not contain.
