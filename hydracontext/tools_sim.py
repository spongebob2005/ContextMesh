"""Simulated MCP tool implementations.

The tools are the ones seeded into the graph (names and schemas match
seed_data.TOOL_TEMPLATES). They return deterministic, service-specific
payloads so demo runs are reproducible without real MCP servers.
"""
from __future__ import annotations

import json
from typing import Any, Callable

FAILING_SERVICES = {"checkout-api"}
DEGRADED_SERVICES = {"search-api"}

REPOS = {"checkout-api": "acme/checkout-api", "payments-api": "acme/payments-api"}
NAMESPACES = {"prod-us": "prod-us", "prod-eu": "prod-eu", "staging": "staging"}


def _generic(service: str | None) -> dict:
    return {"service": service or "unknown", "status": "ok"}


def get_ci_status(service: str = "", **_: Any) -> dict:
    repo = REPOS.get(service, "acme/unknown")
    if service in FAILING_SERVICES:
        return {"repo": repo, "latest_run": "failed", "failed_step": "integration-tests", "commit": "c41f9a2"}
    return {"repo": repo, "latest_run": "passed", "commit": "c41f9a2"}


def list_recent_commits(service: str = "", **_: Any) -> list:
    repo = REPOS.get(service, "acme/unknown")
    commits = [
        {"repo": repo, "sha": "c41f9a2", "message": "bump payments client timeout"},
        {"repo": repo, "sha": "9d20b1c", "message": "add retry on 5xx"},
    ]
    if service in FAILING_SERVICES:
        commits[0]["message"] = "switch checkout session store to redis cluster"
    return commits


def create_issue(title: str = "", body: str = "", **_: Any) -> dict:
    return {"created": True, "issue": f"ISS-{abs(hash(title)) % 900 + 100}", "title": title}


def get_pod_status(namespace: str = "prod-us", **_: Any) -> dict:
    pods = []
    for svc in ("checkout-api", "payments-api", "auth-service", "search-api"):
        restarts = 7 if (svc in FAILING_SERVICES and namespace.startswith("prod")) else 0
        pods.append({"pod": f"{svc}-7d9f", "namespace": namespace, "ready": "1/1", "restarts": restarts})
    return {"namespace": namespace, "pods": pods}


def get_events(namespace: str = "prod-us", **_: Any) -> dict:
    evs = [{"kind": "Warning", "reason": "BackOff", "object": "checkout-api-7d9f"}] \
        if namespace.startswith("prod") else []
    return {"namespace": namespace, "events": evs}


def restart_deployment(namespace: str = "prod-us", service: str = "", **_: Any) -> dict:
    return {"restarted": True, "deployment": service or "unknown", "namespace": namespace}


def scale_deployment(namespace: str = "prod-us", service: str = "", replicas: int = 0, **_: Any) -> dict:
    return {"scaled": True, "deployment": service, "replicas": replicas, "namespace": namespace}


def get_slow_queries(dataset: str = "orders-db", **_: Any) -> list:
    if dataset == "orders-db":
        return [
            {"query": "SELECT ... FROM orders WHERE customer_id=$1", "mean_ms": 4200, "calls": 1337},
            {"query": "SELECT ... FROM order_items JOIN orders", "mean_ms": 980, "calls": 21000},
        ]
    return []


def get_replication_lag(dataset: str = "orders-db", **_: Any) -> dict:
    if dataset == "orders-db":
        return {"dataset": dataset, "standbys": [{"name": "replica-1", "lag_seconds": 143}, {"name": "replica-2", "lag_seconds": 12}]}
    return {"dataset": dataset, "standbys": [{"name": "replica-1", "lag_seconds": 2}]}


def run_readonly_query(dataset: str = "", sql: str = "", **_: Any) -> dict:
    return {"dataset": dataset, "rows": [], "note": "simulated read-only execution"}


def get_metric_series(service: str = "", metric: str = "http_error_rate", window: str = "1h", **_: Any) -> list:
    base = 14.0 if service in FAILING_SERVICES else (2.0 if service in DEGRADED_SERVICES else 0.2)
    return [{"metric": metric, "service": service, "window": window,
             "series": [{"t": f"+{m}m", "value": round(base + (m % 7) * base * 0.05, 3)} for m in range(0, 60, 10)]}]


def get_dashboard(service: str = "", **_: Any) -> dict:
    return {"service": service, "panels": ["http_error_rate", "p99_latency", "saturation"]}


def get_incidents(service: str = "", **_: Any) -> list:
    if service in FAILING_SERVICES:
        return [{"id": "INC-4471", "service": service, "status": "triggered", "summary": "error rate > 10%"}]
    return []


def get_oncall(service: str = "", **_: Any) -> dict:
    oncalls = {"checkout-api": "sam", "payments-api": "dana", "auth-service": "sam"}
    return {"service": service, "oncall": oncalls.get(service, "primary-rotation")}


def acknowledge_incident(id: str = "", **_: Any) -> dict:
    return {"acknowledged": True, "id": id}


IMPLS: dict[str, Callable[..., Any]] = {
    "get_ci_status": get_ci_status,
    "list_recent_commits": list_recent_commits,
    "create_issue": create_issue,
    "get_pod_status": get_pod_status,
    "get_events": get_events,
    "restart_deployment": restart_deployment,
    "scale_deployment": scale_deployment,
    "get_slow_queries": get_slow_queries,
    "get_replication_lag": get_replication_lag,
    "run_readonly_query": run_readonly_query,
    "get_metric_series": get_metric_series,
    "get_dashboard": get_dashboard,
    "get_incidents": get_incidents,
    "get_oncall": get_oncall,
    "acknowledge_incident": acknowledge_incident,
}


def invoke_tool(name: str, args: dict) -> str:
    fn = IMPLS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        return json.dumps(fn(**args))
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})
