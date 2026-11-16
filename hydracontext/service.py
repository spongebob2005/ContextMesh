"""ContextMesh — the agent context layer as a product endpoint.

Reads (plan) are fully concurrent; writes (record_session) are serialized
per process, matching HydraDB's single-writer-per-cell design.

Run:   uvicorn hydracontext.service:app --port 8000
Try:   curl -s localhost:8000/v1/plan -H 'Content-Type: application/json' \
         -d '{"task":"why is checkout failing in prod"}'
UI:    http://localhost:8000/
Docs:  http://localhost:8000/docs   (OpenAPI: /openapi.json)

Environment:
  CONTEXTSMESH_CORS_ORIGINS  comma-separated origins, or "*" (default "*")
  CONTEXTSMESH_API_KEY       optional API key; when set, /v1/plan, /v1/session,
                             and /v1/stats require X-API-Key: <key> or
                             Authorization: Bearer <key>
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import CONFIG
from .store import HydraContextStore

logger = logging.getLogger("contextmesh")

# --------------------------------------------------------------------- app

app = FastAPI(
    title="ContextMesh API",
    version="0.2.0",
    description=(
        "Context packs for agent fleets. Send a task to `POST /v1/plan` and "
        "get back the skills, tool schemas, MCP servers, and resolved entities "
        "that task needs — planned by a HydraDB graph traversal in two "
        "round-trips. Write usage back with `POST /v1/session`.\n\n"
        "Reads are concurrent; session writes are serialized per process "
        "(HydraDB admits one writer per cell). Authentication is optional in "
        "this build: set `CONTEXTSMESH_API_KEY` to require `X-API-Key` or "
        "`Authorization: Bearer` on `/v1/*`, or terminate auth at your gateway."
    ),
    servers=[{"url": "http://localhost:8000", "description": "Self-hosted service"}],
    openapi_tags=[
        {"name": "plan", "description": "Plan the context for a task."},
        {"name": "session", "description": "Record what an agent used."},
        {"name": "ops", "description": "Health, readiness, and graph stats."},
        {"name": "pilot", "description": "Pilot requests from the website."},
    ],
)

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CONTEXTSMESH_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["*"],
    allow_credentials=False,  # no cookies; keeps "*" legal
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

store = HydraContextStore()
write_lock = threading.Lock()
pilot_lock = threading.Lock()

SITE_DIR = Path(__file__).resolve().parent.parent / "site"
BRAND_DIR = Path(__file__).resolve().parent.parent / "brand"
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
RUNTIME_DIR = Path(__file__).resolve().parent.parent / ".runtime"

API_KEY = os.getenv("CONTEXTSMESH_API_KEY", "").strip()

# Serve the product website (site/) with fallbacks for the legacy demo (web/).
if SITE_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=SITE_DIR / "assets"), name="assets")
    if BRAND_DIR.is_dir():
        app.mount("/brand", StaticFiles(directory=BRAND_DIR), name="brand")


# ------------------------------------------------------------------ schemas


class PlanRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task": "why is checkout failing in prod",
                "top_k": 3,
            }
        }
    )

    task: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The task in human language.",
        examples=["why is checkout failing in prod"],
    )
    top_k: int = Field(
        3,
        ge=1,
        le=10,
        description="Maximum number of matching skills to traverse.",
    )


class EntityOut(BaseModel):
    entity_id: int | None = Field(None, description="Graph vertex id of the entity.")
    name: str = Field(..., description="Canonical name, e.g. checkout-api.")
    kind: str | None = Field(None, description="service, database, environment, ...")


class ToolOut(BaseModel):
    id: int | None = None
    tool: str = Field(..., description="Tool name to bind in the agent runtime.")
    kind: str | None = None
    tool_schema: str | None = Field(
        None,
        alias="schema_json",
        description="JSON schema for the tool.",
    )
    server: str | None = Field(None, description="MCP server that serves the tool.")
    server_id: int | None = None


class MCPServerOut(BaseModel):
    id: int | None = None
    name: str = Field(..., description="MCP server name, e.g. k8s.")
    command: str | None = Field(None, description="Command that starts the server.")


class PlanResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "skills": ["incident-triage"],
                "tools": [
                    {
                        "id": 205,
                        "tool": "get_events",
                        "kind": "mcp_tool",
                        "schema_json": "{\"name\":\"get_events\",...}",
                        "server": "k8s",
                        "server_id": 303,
                    }
                ],
                "mcp_servers": [
                    {"id": 303, "name": "k8s", "command": "npx -y mcp-server-kubernetes"}
                ],
                "resolved_entities": {
                    "checkout": {"entity_id": 402, "name": "checkout-api", "kind": "service"},
                    "prod": {"entity_id": 406, "name": "prod-us", "kind": "environment"},
                },
                "graph_round_trips": 2,
                "context_ms": 7.0,
            }
        }
    )

    skills: list[str] = Field(..., description="Matched skill names.")
    tools: list[ToolOut] = Field(..., description="Only the tools this task needs.")
    mcp_servers: list[MCPServerOut] = Field(..., description="Servers behind those tools.")
    resolved_entities: dict[str, EntityOut] = Field(
        ..., description="Mention -> canonical entity."
    )
    graph_round_trips: int = Field(..., description="Graph queries used to build the pack.")
    context_ms: float = Field(..., description="Time spent in the graph, in milliseconds.")


class SessionRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task": "why is checkout failing in prod",
                "used_tools": ["get_pod_status", "get_events"],
                "resolutions": {"checkout": "checkout-api", "prod": "prod-us"},
            }
        }
    )

    task: str = Field(..., min_length=1, max_length=2000)
    used_tools: list[str] = Field(
        default_factory=list,
        max_length=64,
        description="Tool names the agent actually called.",
    )
    resolutions: dict[str, str] = Field(
        default_factory=dict,
        description="Mention -> canonical entity name the agent used.",
    )


class SessionResponse(BaseModel):
    session_id: str = Field(..., description="Id of the recorded Session vertex.")


class HealthResponse(BaseModel):
    ok: bool
    graph: str
    graph_reachable: bool


class StatsResponse(BaseModel):
    Skill: int
    Tool: int
    MCPServer: int
    Entity: int
    Alias: int
    Session: int


class PilotRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Ada Lovelace",
                "email": "ada@example.com",
                "company": "Analytical Engines",
                "note": "Two LangGraph agents, ~40 tasks/day.",
            }
        }
    )

    name: str = Field(..., min_length=1, max_length=120)
    email: str = Field(
        ...,
        min_length=3,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Work email.",
    )
    company: str = Field("", max_length=160)
    note: str = Field("", max_length=2000, description="What are you building?")


class PilotResponse(BaseModel):
    ok: bool
    message: str


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Stable machine-readable error code.")
    message: str = Field(..., description="Human-readable summary.")
    request_id: str | None = Field(None, description="Request ID for support and logs.")
    details: list[dict[str, Any]] | None = Field(
        None, description="Validation details, when applicable."
    )


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "graph_unavailable",
                    "message": "Graph backend unavailable.",
                    "request_id": "9f2c1a7b4e01",
                }
            }
        }
    )

    error: ErrorDetail


ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Missing or invalid API key."},
    422: {"model": ErrorResponse, "description": "Request validation failed."},
    500: {"model": ErrorResponse, "description": "Unexpected server error."},
}
GRAPH_ERROR_RESPONSES = {
    **ERROR_RESPONSES,
    503: {"model": ErrorResponse, "description": "HydraDB is unavailable."},
}


# ------------------------------------------------------------------- middleware


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# --------------------------------------------------------------------- errors


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "request failed"
    code = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        429: "rate_limited",
        503: "graph_unavailable",
    }.get(exc.status_code, "http_error")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": detail,
                "request_id": _request_id(request),
            }
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "invalid_request",
                "message": "Request validation failed.",
                "request_id": _request_id(request),
                "details": json.loads(json.dumps(exc.errors(), default=str)),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Unexpected server error.",
                "request_id": _request_id(request),
            }
        },
    )


# ----------------------------------------------------------------------- auth


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def require_api_key(
    key: str | None = Depends(api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """Optional API-key auth. Off unless CONTEXTSMESH_API_KEY is set."""
    if not API_KEY:
        return
    token = (key or "").strip()
    if not token and credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials.strip()
    if not token or not hmac.compare_digest(token, API_KEY):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _graph_call(operation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return operation(*args, **kwargs)
    except (httpx.HTTPError, RuntimeError) as exc:
        logger.warning("HydraDB request failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Graph backend unavailable.",
        ) from exc


# ------------------------------------------------------------------- website


@app.get("/", include_in_schema=False)
def ui():
    index = SITE_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return FileResponse(WEB_DIR / "index.html")


@app.get("/styles.css", include_in_schema=False)
def styles():
    path = SITE_DIR / "styles.css"
    return FileResponse(path) if path.is_file() else FileResponse(WEB_DIR / "styles.css")


@app.get("/app.js", include_in_schema=False)
def app_js():
    path = SITE_DIR / "app.js"
    return FileResponse(path) if path.is_file() else FileResponse(WEB_DIR / "app.js")


@app.get("/fixtures.js", include_in_schema=False)
def fixtures():
    path = SITE_DIR / "fixtures.js"
    return FileResponse(path) if path.is_file() else FileResponse(WEB_DIR / "fixtures.js")


# ----------------------------------------------------------------------- ops


def _graph_reachable() -> bool:
    reachable = store.ping()
    if not reachable:
        logger.warning("graph health check failed")
    return reachable


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["ops"],
    summary="Liveness and graph reachability",
)
def health():
    reachable = _graph_reachable()
    return {"ok": True, "graph": CONFIG.namespace, "graph_reachable": reachable}


@app.get(
    "/ready",
    response_model=HealthResponse,
    tags=["ops"],
    summary="Readiness (503 when the graph is unreachable)",
    responses={503: {"model": HealthResponse}},
)
def ready():
    reachable = _graph_reachable()
    body = {"ok": reachable, "graph": CONFIG.namespace, "graph_reachable": reachable}
    return JSONResponse(status_code=200 if reachable else 503, content=body)


@app.get(
    "/v1/stats",
    response_model=StatsResponse,
    tags=["ops"],
    summary="Graph counts by label",
    dependencies=[Depends(require_api_key)],
    responses=GRAPH_ERROR_RESPONSES,
)
def stats():
    return _graph_call(store.stats)


# ---------------------------------------------------------------------- plan


@app.post(
    "/v1/plan",
    response_model=PlanResponse,
    tags=["plan"],
    summary="Plan context for a task",
    description=(
        "Returns the skills matched for the task, only the tools those skills "
        "need, the MCP servers behind them, and mention-to-entity resolutions. "
        "Two graph round-trips for the demo graph."
    ),
    dependencies=[Depends(require_api_key)],
    responses=GRAPH_ERROR_RESPONSES,
)
def plan(req: PlanRequest):
    pack = _graph_call(store.plan, req.task, top_k=req.top_k)
    return {
        "skills": [s["name"] for s in pack.skills],
        "tools": pack.tools,
        "mcp_servers": pack.mcp_servers,
        "resolved_entities": pack.entities,
        "graph_round_trips": pack.round_trips(),
        "context_ms": round(sum(ms for _, ms in pack.queries), 1),
    }


# ------------------------------------------------------------------- session


@app.post(
    "/v1/session",
    response_model=SessionResponse,
    tags=["session"],
    summary="Record what the agent used",
    description=(
        "Writes one Session vertex, increments usage counters for the tools "
        "actually called, and learns mention->entity aliases. Writes are "
        "serialized per process to match HydraDB's one-writer-per-cell model."
    ),
    dependencies=[Depends(require_api_key)],
    responses=GRAPH_ERROR_RESPONSES,
)
def session(req: SessionRequest):
    with write_lock:  # HydraDB: at most one writer per cell
        sid = _graph_call(
            store.record_session, req.task, req.used_tools, req.resolutions
        )
    return {"session_id": sid}


# --------------------------------------------------------------------- pilot


@app.post(
    "/v1/pilot",
    response_model=PilotResponse,
    tags=["pilot"],
    summary="Request a pilot",
    description="Stores a pilot request from the website as a JSON line.",
    responses={
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
    },
)
def pilot(req: PilotRequest):
    record = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "name": req.name,
        "email": req.email,
        "company": req.company,
        "note": req.note,
    }
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNTIME_DIR / "pilots.jsonl"
    with pilot_lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"ok": True, "message": "Thanks — we'll be in touch."}
