// Recorded from the live graph, used only when the API is unreachable.
window.FALLBACK_PACKS = {
  "why is checkout failing in prod": {
    "skills": [
      "incident-triage"
    ],
    "tools": [
      {
        "tool": "get_ci_status",
        "server": "github",
        "desc": "Get the CI status of the latest runs for a repository."
      },
      {
        "tool": "get_events",
        "server": "k8s",
        "desc": "Get recent Kubernetes events for a namespace."
      },
      {
        "tool": "get_incidents",
        "server": "pagerduty",
        "desc": "List open incidents, optionally filtered by service."
      },
      {
        "tool": "get_metric_series",
        "server": "grafana",
        "desc": "Get a metric time series for a service over a window."
      },
      {
        "tool": "get_pod_status",
        "server": "k8s",
        "desc": "Get pod status, restarts and images for a namespace."
      }
    ],
    "mcp_servers": [
      "github",
      "k8s",
      "pagerduty",
      "grafana"
    ],
    "entities": {
      "checkout": {
        "name": "checkout-api",
        "kind": "service"
      },
      "prod": {
        "name": "prod-us",
        "kind": "environment"
      }
    },
    "trips": 2,
    "ms": 3.9
  },
  "is orders lagging? check replication": {
    "skills": [
      "db-health-check"
    ],
    "tools": [
      {
        "tool": "get_replication_lag",
        "server": "postgres",
        "desc": "Get replication lag in seconds per standby."
      },
      {
        "tool": "get_slow_queries",
        "server": "postgres",
        "desc": "List the slowest queries with their mean runtime."
      },
      {
        "tool": "run_readonly_query",
        "server": "postgres",
        "desc": "Run a read-only SQL query against an allowlisted dataset."
      }
    ],
    "mcp_servers": [
      "postgres"
    ],
    "entities": {
      "orders": {
        "name": "orders-db",
        "kind": "database"
      }
    },
    "trips": 2,
    "ms": 2.9
  },
  "scale search in staging": {
    "skills": [
      "capacity-scaling"
    ],
    "tools": [
      {
        "tool": "get_metric_series",
        "server": "grafana",
        "desc": "Get a metric time series for a service over a window."
      },
      {
        "tool": "get_pod_status",
        "server": "k8s",
        "desc": "Get pod status, restarts and images for a namespace."
      },
      {
        "tool": "scale_deployment",
        "server": "k8s",
        "desc": "Scale a deployment to N replicas."
      }
    ],
    "mcp_servers": [
      "grafana",
      "k8s"
    ],
    "entities": {
      "search": {
        "name": "search-api",
        "kind": "service"
      },
      "staging": {
        "name": "staging",
        "kind": "environment"
      }
    },
    "trips": 2,
    "ms": 2.9
  },
  "page the oncall for payments": {
    "skills": [
      "escalation-oncall",
      "incident-triage"
    ],
    "tools": [
      {
        "tool": "acknowledge_incident",
        "server": "pagerduty",
        "desc": "Acknowledge an incident by id."
      },
      {
        "tool": "create_issue",
        "server": "github",
        "desc": "Open a GitHub issue with a title and body."
      },
      {
        "tool": "get_incidents",
        "server": "pagerduty",
        "desc": "List open incidents, optionally filtered by service."
      },
      {
        "tool": "get_oncall",
        "server": "pagerduty",
        "desc": "Get the current on-call engineer for a service."
      },
      {
        "tool": "get_ci_status",
        "server": "github",
        "desc": "Get the CI status of the latest runs for a repository."
      },
      {
        "tool": "get_events",
        "server": "k8s",
        "desc": "Get recent Kubernetes events for a namespace."
      },
      {
        "tool": "get_metric_series",
        "server": "grafana",
        "desc": "Get a metric time series for a service over a window."
      },
      {
        "tool": "get_pod_status",
        "server": "k8s",
        "desc": "Get pod status, restarts and images for a namespace."
      }
    ],
    "mcp_servers": [
      "pagerduty",
      "github",
      "k8s",
      "grafana"
    ],
    "entities": {
      "payments": {
        "name": "payments-api",
        "kind": "service"
      }
    },
    "trips": 2,
    "ms": 4.3
  }
};
