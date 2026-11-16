"""Central configuration for the HydraContext demo, from env vars."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str) -> str:
    value = os.getenv(key, default)
    # `null` means absent to HydraDB's env parser; keep it out of our values.
    return value if value and value != "null" else default


@dataclass(frozen=True)
class HydraConfig:
    # HTTP query API (batch/parameters are the documented-verified path)
    http_uri: str = field(default_factory=lambda: _env("HYDRA_HTTP_URI", "http://127.0.0.1:8443"))
    token: str = field(default_factory=lambda: _env("HYDRA_TOKEN", "hydra-hackathon-local-dev-token-32ch"))
    # namespace header (X-Graph-Namespace); the path uses the graph id
    namespace: str = field(default_factory=lambda: _env("HYDRA_NAMESPACE", "agent"))
    graph_id: str = field(default_factory=lambda: _env("HYDRA_GRAPH_ID", "default"))
    cell_id: str = field(default_factory=lambda: _env("HYDRA_CELL_ID", "cell-0"))
    agent_id: str = field(default_factory=lambda: _env("HYDRA_AGENT_ID", "agent-0"))

    @property
    def query_url(self) -> str:
        return f"{self.http_uri}/v1/graphs/{self.graph_id}/query"


CONFIG = HydraConfig()
