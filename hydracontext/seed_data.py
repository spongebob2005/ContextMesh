"""Seed content: an SRE/ops agent's world.

Five MCP servers, fifteen tools, six skills, and a set of services and
databases the agent must resolve from the way people actually talk
("checkout is down", "is orders-db lagging?").
"""
from __future__ import annotations

import json

SERVERS = [
    {"id": "mcp:github", "name": "github", "command": "npx -y @modelcontextprotocol/server-github", "url": ""},
    {"id": "mcp:k8s", "name": "k8s", "command": "npx -y mcp-server-kubernetes", "url": ""},
    {"id": "mcp:postgres", "name": "postgres", "command": "npx -y @modelcontextprotocol/server-postgres", "url": ""},
    {"id": "mcp:grafana", "name": "grafana", "command": "npx -y @mcp/grafana", "url": ""},
    {"id": "mcp:pagerduty", "name": "pagerduty", "command": "npx -y @mcp/pagerduty", "url": ""},
]

TOOL_TEMPLATES = {
    "get_ci_status": ("github", "Get the CI status of the latest runs for a repository."),
    "list_recent_commits": ("github", "List recent commits on the default branch of a repository."),
    "create_issue": ("github", "Open a GitHub issue with a title and body."),
    "get_pod_status": ("k8s", "Get pod status, restarts and images for a namespace."),
    "get_events": ("k8s", "Get recent Kubernetes events for a namespace."),
    "restart_deployment": ("k8s", "Restart a deployment in a namespace."),
    "scale_deployment": ("k8s", "Scale a deployment to N replicas."),
    "get_slow_queries": ("postgres", "List the slowest queries with their mean runtime."),
    "get_replication_lag": ("postgres", "Get replication lag in seconds per standby."),
    "run_readonly_query": ("postgres", "Run a read-only SQL query against an allowlisted dataset."),
    "get_metric_series": ("grafana", "Get a metric time series for a service over a window."),
    "get_dashboard": ("grafana", "Fetch a dashboard snapshot by service and panel name."),
    "get_incidents": ("pagerduty", "List open incidents, optionally filtered by service."),
    "get_oncall": ("pagerduty", "Get the current on-call engineer for a service."),
    "acknowledge_incident": ("pagerduty", "Acknowledge an incident by id."),
}

SKILLS = {
    "incident-triage": {
        "keywords": ["incident", "outage", "failing", "down", "broken", "error", "alerts", "page", "ci", "deploy"],
        "tools": ["get_ci_status", "get_pod_status", "get_events", "get_metric_series", "get_incidents"],
    },
    "log-investigation": {
        "keywords": ["logs", "deploy", "commits", "changes", "recent", "ci"],
        "tools": ["list_recent_commits", "get_ci_status"],
    },
    "db-health-check": {
        "keywords": ["database", "db", "lag", "replication", "slow", "queries", "health"],
        "tools": ["get_replication_lag", "get_slow_queries", "run_readonly_query"],
    },
    "capacity-scaling": {
        "keywords": ["scale", "capacity", "replicas", "autoscale", "cpu", "traffic"],
        "tools": ["scale_deployment", "get_metric_series", "get_pod_status"],
    },
    "service-recovery": {
        "keywords": ["restart", "recover", "rollback", "fix", "restore"],
        "tools": ["restart_deployment", "scale_deployment", "acknowledge_incident"],
    },
    "escalation-oncall": {
        "keywords": ["oncall", "page", "escalate", "incident", "acknowledge", "ticket", "issue"],
        "tools": ["get_oncall", "acknowledge_incident", "create_issue", "get_incidents"],
    },
}

# how people actually refer to things -> canonical entities
ENTITIES = {
    "checkout-api": {"kind": "service"},
    "payments-api": {"kind": "service"},
    "auth-service": {"kind": "service"},
    "search-api": {"kind": "service"},
    "orders-db": {"kind": "database"},
    "users-db": {"kind": "database"},
    "prod-us": {"kind": "environment"},
    "prod-eu": {"kind": "environment"},
    "staging": {"kind": "environment"},
}

ALIASES = {
    "checkout": "checkout-api",
    "payments": "payments-api",
    "payment": "payments-api",
    "auth": "auth-service",
    "search": "search-api",
    "orders": "orders-db",
    "users": "users-db",
    "prod": "prod-us",
    "production": "prod-us",
    "staging": "staging",
}


def _server_ids() -> dict[str, int]:
    """Deterministic integer ids: sorted server names -> 301+i."""
    return {s["name"]: 301 + i for i, s in enumerate(sorted(SERVERS, key=lambda s: s["name"]))}


def _tool_ids() -> dict[str, int]:
    """Deterministic integer ids: sorted tool names -> 201+i."""
    return {name: 201 + i for i, name in enumerate(sorted(TOOL_TEMPLATES))}


def _skill_ids() -> dict[str, int]:
    return {name: 101 + i for i, name in enumerate(sorted(SKILLS))}


def _entity_ids() -> dict[str, int]:
    return {eid: 401 + i for i, eid in enumerate(sorted(ENTITIES))}


def _alias_ids() -> dict[str, int]:
    return {text: 501 + i for i, text in enumerate(sorted(ALIASES))}


def build_seed() -> dict:
    tool_ids = _tool_ids()
    skill_ids = _skill_ids()
    entity_ids = _entity_ids()
    alias_ids = _alias_ids()
    server_ids = _server_ids()

    tools = []
    tool_to_server: dict[str, str] = {}
    for name, (server, description) in sorted(TOOL_TEMPLATES.items()):
        tool_to_server[name] = server
        tools.append(
            {
                "id": tool_ids[name],
                "name": name,
                "kind": "mcp_tool",
                "endpoint": f"mcp:{server}",
                "uses": 0,
                "schema_json": json.dumps(
                    {
                        "name": name,
                        "description": description,
                        "server": server,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "service": {"type": "string", "description": "canonical service id"},
                                "namespace": {"type": "string"},
                                "window": {"type": "string"},
                            },
                        },
                    }
                ),
            }
        )

    skills = [
        {"id": skill_ids[name], "name": name, "keywords": json.dumps(spec["keywords"]), "uses": 0}
        for name, spec in sorted(SKILLS.items())
    ]

    servers = [
        {
            "id": server_ids[s["name"]],
            "name": s["name"],
            "command": s["command"],
            "url": s["url"],
        }
        for s in sorted(SERVERS, key=lambda s: s["name"])
    ]

    entities = [
        {"id": entity_ids[eid], "canonical_name": eid, "kind": spec["kind"]}
        for eid, spec in sorted(ENTITIES.items())
    ]
    aliases = [
        {"id": alias_ids[text], "text": text} for text in sorted(ALIASES)
    ]

    membership = {
        "HAS_SKILL": [{"src": 1, "dst": sid} for sid in skill_ids.values()],
        "NEEDS": [
            {"src": skill_ids[sname], "dst": tool_ids[t]}
            for sname, spec in SKILLS.items()
            for t in spec["tools"]
        ],
        "SERVED_BY": [
            {"src": tool_ids[t], "dst": server_ids[srv]}
            for t, srv in tool_to_server.items()
        ],
        "RESOLVES_TO": [
            {"src": alias_ids[text], "dst": entity_ids[eid]}
            for text, eid in ALIASES.items()
        ],
    }
    return {
        "servers": servers,
        "tools": tools,
        "skills": skills,
        "entities": entities,
        "aliases": aliases,
        "membership": membership,
    }
