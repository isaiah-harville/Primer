"""Prometheus metrics, with no label that can carry content.

Label cardinality is the usual reason to be careful here, but for Primer the
first reason is disclosure: a metric labelled by query text or filename
publishes both to anyone who can read the metrics endpoint, which is
typically the whole cluster.

Labels are therefore closed sets - a stage name, an outcome, a backend -
and never a value taken from a user.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from prometheus_client import CollectorRegistry, Counter, Histogram

#: Buckets chosen for what these operations actually take: a search in
#: milliseconds, an ingestion stage in minutes.
LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 300, 900)


@dataclass
class Metrics:
    """The instruments a Primer service records."""

    registry: CollectorRegistry = field(default_factory=CollectorRegistry)

    def __post_init__(self) -> None:
        self.requests = Counter(
            "primer_requests_total",
            "HTTP requests handled.",
            # The route template, never the resolved path: a path carries
            # library and document ids, and those identify people's things.
            ["service", "method", "route", "status"],
            registry=self.registry,
        )
        self.request_latency = Histogram(
            "primer_request_duration_seconds",
            "How long requests take.",
            ["service", "route"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.stage_duration = Histogram(
            "primer_ingestion_stage_duration_seconds",
            "How long an ingestion stage takes.",
            ["stage", "outcome"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.jobs = Counter(
            "primer_ingestion_jobs_total",
            "Ingestion jobs by terminal state.",
            ["stage", "state"],
            registry=self.registry,
        )
        self.queue_age = Histogram(
            "primer_ingestion_queue_age_seconds",
            "How long a job waited before a worker claimed it.",
            ["stage"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.searches = Counter(
            "primer_searches_total",
            "Retrieval searches by backend.",
            ["backend", "outcome"],
            registry=self.registry,
        )
        self.time_to_first_token = Histogram(
            "primer_chat_first_token_seconds",
            "Time from question to first streamed fragment.",
            ["outcome"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.tool_decisions = Counter(
            "primer_tool_decisions_total",
            "Tool calls by decision.",
            # The tool's configured name is an operator's string, not a
            # user's, so it is safe to label with.
            ["tool", "decision"],
            registry=self.registry,
        )


def configure_metrics() -> Metrics:
    """Build a service's instruments.

    Returned rather than global, so a test can assert on a registry that
    belongs to it and two services in one process cannot collide.
    """
    return Metrics()
