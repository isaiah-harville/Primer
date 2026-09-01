"""Static assertions over the rendered Helm chart.

These render the templates and read the result, rather than deploying
anything. What they guard is the set of mistakes that stay invisible until
someone is already relying on the deployment: a service reachable that
should not be, an identity header believed that should have been stripped, a
secret written into a manifest.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / "deploy" / "helm" / "primer"

#: Enough to satisfy every `required` in the chart. None is a real value.
BASE_VALUES = [
    "postgresql.existingSecret=primer-postgres",
    "rabbitmq.existingSecret=primer-rabbitmq",
    "auth.oidc.issuerUrl=https://idp.example.com/",
    "auth.oidc.clientId=primer",
    "auth.oidc.existingSecret=primer-oidc",
    "inference.chat.baseUrl=http://model/v1",
    "inference.chat.model=chat-model",
    "inference.embeddings.baseUrl=http://model/v1",
    "inference.embeddings.model=embed-model",
    "ingress.host=primer.example.com",
]


def render(*overrides: str) -> list[dict[str, Any]]:
    if shutil.which("helm") is None:
        pytest.skip("helm is not installed")
    command = ["helm", "template", "primer", str(CHART)]
    for value in [*BASE_VALUES, *overrides]:
        command += ["--set", value]
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        pytest.fail(f"helm template failed:\n{result.stderr}")
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


@pytest.fixture(scope="module")
def manifests() -> list[dict[str, Any]]:
    return render()


def of_kind(manifests: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [doc for doc in manifests if doc.get("kind") == kind]


def named(manifests: list[dict[str, Any]], kind: str, suffix: str) -> dict[str, Any]:
    for doc in of_kind(manifests, kind):
        if doc["metadata"]["name"].endswith(suffix):
            return doc
    pytest.fail(f"no {kind} ending in {suffix}")


def containers(deployment: dict[str, Any]) -> list[dict[str, Any]]:
    return deployment["spec"]["template"]["spec"]["containers"]


def test_no_service_is_exposed_outside_the_cluster(manifests: list[dict[str, Any]]) -> None:
    """Control trusts its identity headers.

    Anything that could reach it directly could set those headers itself and
    be any user, so every service is ClusterIP and the ingress is the only
    way in. This is the single most important assertion in this file.
    """
    services = of_kind(manifests, "Service")
    # Guard against a vacuous pass: rendering nothing would satisfy the loop.
    assert len(services) >= 4

    for service in services:
        assert service["spec"]["type"] == "ClusterIP", service["metadata"]["name"]


def test_the_ingress_strips_inbound_identity_headers(manifests: list[dict[str, Any]]) -> None:
    """A request arriving with its own X-Auth-Request-User must not keep it."""
    ingress = of_kind(manifests, "Ingress")[0]
    snippet = ingress["metadata"]["annotations"][
        "nginx.ingress.kubernetes.io/configuration-snippet"
    ]

    for header in (
        "X-Auth-Request-User",
        "X-Auth-Request-Email",
        "X-Auth-Request-Groups",
        "X-Forwarded-User",
    ):
        assert header in snippet, f"{header} is not stripped"
    assert "more_clear_input_headers" in snippet


def test_the_ingress_routes_only_to_the_authenticating_proxy(
    manifests: list[dict[str, Any]],
) -> None:
    """No path reaches Control, Chat, or Retrieval directly."""
    ingress = of_kind(manifests, "Ingress")[0]
    backends = {
        path["backend"]["service"]["name"]
        for rule in ingress["spec"]["rules"]
        for path in rule["http"]["paths"]
    }

    assert backends == {"primer-primer-auth"}


def test_streaming_is_not_buffered(manifests: list[dict[str, Any]]) -> None:
    """Buffering would hold every token until the answer finished."""
    annotations = of_kind(manifests, "Ingress")[0]["metadata"]["annotations"]
    assert annotations["nginx.ingress.kubernetes.io/proxy-buffering"] == "off"


def test_every_pod_runs_unprivileged(manifests: list[dict[str, Any]]) -> None:
    deployments = of_kind(manifests, "Deployment")
    assert len(deployments) >= 6

    for deployment in deployments:
        pod = deployment["spec"]["template"]["spec"]
        assert pod["securityContext"]["runAsNonRoot"] is True, deployment["metadata"]["name"]
        for container in containers(deployment):
            security = container["securityContext"]
            assert security["allowPrivilegeEscalation"] is False
            assert security["readOnlyRootFilesystem"] is True
            assert security["capabilities"]["drop"] == ["ALL"]


def test_no_credential_is_written_into_a_manifest(manifests: list[dict[str, Any]]) -> None:
    """A value in a manifest is a value in `kubectl get deployment -o yaml`."""
    for deployment in of_kind(manifests, "Deployment"):
        for container in containers(deployment):
            for entry in container.get("env", []):
                if entry["name"].endswith(("_TOKEN", "_API_KEY", "_SECRET", "_URL")):
                    if entry["name"].endswith("_URL") and "value" in entry:
                        # Service URLs and model endpoints are not secrets.
                        continue
                    assert "value" not in entry, f"{entry['name']} is inlined"
                    assert "valueFrom" in entry


def test_the_database_url_comes_from_a_secret(manifests: list[dict[str, Any]]) -> None:
    control = named(manifests, "Deployment", "-control")
    entry = next(e for e in containers(control)[0]["env"] if e["name"] == "PRIMER_DATABASE_URL")

    assert entry["valueFrom"]["secretKeyRef"]["name"] == "primer-postgres"


def test_migrations_run_once_per_release_not_once_per_pod(
    manifests: list[dict[str, Any]],
) -> None:
    """Three replicas racing to alter one schema is what a hook avoids."""
    jobs = of_kind(manifests, "Job")
    assert len(jobs) == 2

    for job in jobs:
        annotations = job["metadata"]["annotations"]
        assert annotations["helm.sh/hook"] == "pre-install,pre-upgrade"
        assert job["spec"]["template"]["spec"]["restartPolicy"] == "Never"

    for deployment in of_kind(manifests, "Deployment"):
        assert "initContainers" not in deployment["spec"]["template"]["spec"]


def test_parsing_and_indexing_scale_separately(manifests: list[dict[str, Any]]) -> None:
    """Parsing is CPU-heavy and holds documents in memory; indexing waits on a
    network call. One deployment would make them share a bottleneck."""
    parse = named(manifests, "Deployment", "-worker-parse")
    index = named(manifests, "Deployment", "-worker-index")

    parse_queues = containers(parse)[0]["command"][-1]
    index_queues = containers(index)[0]["command"][-1]

    assert parse_queues == "ingestion.parse"
    assert "ingestion.embed" in index_queues
    assert "ingestion.parse" not in index_queues


def test_the_parse_worker_keeps_its_model_cache(manifests: list[dict[str, Any]]) -> None:
    """Without it every pod restart re-downloads half a gigabyte."""
    claims = of_kind(manifests, "PersistentVolumeClaim")
    assert len(claims) == 1

    parse = named(manifests, "Deployment", "-worker-parse")
    mounts = {m["mountPath"] for m in containers(parse)[0]["volumeMounts"]}
    assert "/var/cache/primer/huggingface" in mounts


def test_liveness_and_readiness_differ(manifests: list[dict[str, Any]]) -> None:
    """Restarting a pod because PostgreSQL blipped is when it helps least."""
    control = containers(named(manifests, "Deployment", "-control"))[0]

    assert control["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert control["readinessProbe"]["httpGet"]["path"] == "/health/ready"


def test_every_pod_gets_a_writable_home_on_a_read_only_root(
    manifests: list[dict[str, Any]],
) -> None:
    """Several libraries create a cache directory under $HOME on import."""
    for name in ("-control", "-chat", "-retrieval", "-worker-parse"):
        deployment = named(manifests, "Deployment", name)
        mounts = {m["mountPath"] for m in containers(deployment)[0]["volumeMounts"]}
        # Container paths, not host paths: the read-only root is the point.
        assert {"/tmp", "/home/primer"} <= mounts, name  # noqa: S108


def test_the_proxy_uses_pkce_and_secure_cookies(manifests: list[dict[str, Any]]) -> None:
    """A leaked authorization code should not be enough to finish a sign-in."""
    args = containers(named(manifests, "Deployment", "-auth"))[0]["args"]

    assert "--code-challenge-method=S256" in args
    assert "--cookie-secure=true" in args
    assert "--cookie-httponly=true" in args


def test_the_proxy_sets_the_headers_primer_reads(manifests: list[dict[str, Any]]) -> None:
    args = containers(named(manifests, "Deployment", "-auth"))[0]["args"]
    assert "--set-xauthrequest=true" in args


def test_disabling_auth_removes_the_proxy_entirely() -> None:
    """Not a proxy in a permissive mode: no proxy at all, so there is no
    half-configured edge that looks like it is authenticating."""
    manifests = render("auth.mode=disabled")
    names = [d["metadata"]["name"] for d in of_kind(manifests, "Deployment")]

    assert not any(name.endswith("-auth") for name in names)


def test_qdrant_requires_a_url() -> None:
    """Discovering this on the first search makes it look like a product bug."""
    if shutil.which("helm") is None:
        pytest.skip("helm is not installed")
    command = ["helm", "template", "primer", str(CHART), "--set", "vectorStore.kind=qdrant"]
    for value in BASE_VALUES:
        command += ["--set", value]
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603

    assert result.returncode != 0
    assert "qdrantUrl is required" in result.stderr


def test_the_internal_token_is_generated_not_configured(
    manifests: list[dict[str, Any]],
) -> None:
    """Primer's own cluster-internal credential means nothing outside this
    release, so it is generated rather than asked of the operator."""
    secrets = of_kind(manifests, "Secret")
    assert len(secrets) == 1
    assert "internal-token" in secrets[0]["data"]
