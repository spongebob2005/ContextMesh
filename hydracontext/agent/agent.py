"""LangGraph agents.

Two modes share one execution skeleton and differ only in where their
context comes from:

- "hydra":    `load_context` pulls skills/tools/MCP servers/already-resolved
              entities from HydraDB, and binds ONLY the returned tools.
- "baseline": binds every seeded tool plus a per-mention `lookup_entity`
              tool, so entity resolution happens through extra round-trips.

The measured deltas are context-window size, tool-call count, and wall time.
"""
from __future__ import annotations

import json
import os
from typing import Annotated, Callable, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from ..seed_data import TOOL_TEMPLATES
from ..store import HydraContextStore
from ..tools_sim import IMPLS, invoke_tool

MAX_STEPS = 8


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    task: str
    pack: dict          # hydra mode only
    budget: dict        # instrumentation, mutated by nodes


# --------------------------------------------------------------------- utils

def _llm():
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    return init_chat_model(model, model_provider=provider, temperature=0)


def _add_usage(*usages) -> dict | None:
    total: dict = {}
    seen = False
    for u in usages:
        if not u:
            continue
        seen = True
        for key in ("input_tokens", "output_tokens"):
            total[key] = total.get(key, 0) + (u.get(key) or 0)
    return total if seen else None


def _openai_schemas(descriptions: dict[str, dict]) -> list[dict]:
    """OpenAI-format function schemas for bind_tools."""
    out = []
    for name, schema in descriptions.items():
        out.append({"type": "function", "function": schema})
    return out


def _hydra_schemas(pack: dict) -> dict[str, dict]:
    schemas = {}
    for tool in pack["tools"]:
        try:
            parsed = json.loads(tool["schema_json"])
        except (TypeError, json.JSONDecodeError):
            parsed = {"name": tool["tool"], "description": tool["tool"], "parameters": {}}
        schemas[tool["tool"]] = parsed
    return schemas


def _baseline_schemas() -> dict[str, dict]:
    schemas = {}
    generic_params = {
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "canonical service id"},
            "dataset": {"type": "string", "description": "canonical database id"},
            "namespace": {"type": "string"},
            "window": {"type": "string"},
        },
    }
    for name, (server, description) in TOOL_TEMPLATES.items():
        schemas[name] = {"name": name, "description": description, "parameters": generic_params}
    schemas["lookup_entity"] = {
        "name": "lookup_entity",
        "description": "Resolve one informal mention (e.g. 'checkout') to its canonical id.",
        "parameters": {
            "type": "object",
            "properties": {"mention": {"type": "string", "description": "single informal mention"}},
            "required": ["mention"],
        },
    }
    return schemas


def _tools_node(registry: dict[str, Callable]) -> Callable:
    def node(state: AgentState) -> dict:
        last = state["messages"][-1]
        outs: list[ToolMessage] = []
        for call in last.tool_calls:
            # every call gets a response; unknown names return an error payload
            result = invoke_tool(call["name"], call.get("args", {}))
            outs.append(ToolMessage(content=result, tool_call_id=call["id"]))
            registry["_count"] = registry.get("_count", 0) + 1
        return {"messages": outs}

    return node


# ------------------------------------------------------------------ hydra mode

def _load_context(store: HydraContextStore) -> Callable:
    def node(state: AgentState) -> dict:
        pack = store.plan(state["task"])
        budget = dict(state.get("budget") or {})
        budget["context_round_trips"] = pack.round_trips()
        budget["context_ms"] = round(sum(ms for _, ms in pack.queries), 1)
        return {"pack": pack.to_dict(), "budget": budget}

    return node


HYDRA_SYSTEM = """You are an SRE ops agent. A graph context store has already
pulled exactly the skills, tools, MCP servers, and entity resolutions needed
for this task.

Resolved entities (use these canonical ids in tool calls):
{entities}

Available tools (bound for this task only):
{tools}

Use the canonical entity ids as the `service`/`dataset` arguments. Do not
invent other tools. You MUST call at least one tool before answering: act
now, do not describe what you could do. Answer concisely once you have
enough evidence."""


def _hydra_agent_node(state: AgentState) -> dict:
    pack = state["pack"]
    schemas = _hydra_schemas(pack)
    llm = _llm().bind_tools(_openai_schemas(schemas))
    system = HYDRA_SYSTEM.format(
        entities=json.dumps(pack["entities"], indent=2),
        tools=", ".join(schemas),
    )
    messages = [SystemMessage(content=system), *state["messages"]]
    response = llm.invoke(messages)
    usage = getattr(response, "usage_metadata", None)
    if not response.tool_calls and not any(isinstance(m, ToolMessage) for m in state["messages"]):
        # small models sometimes describe instead of acting; nudge once
        response = llm.invoke(
            [*messages, response, HumanMessage(content="Do not describe. Call a tool now.")]
        )
        extra = getattr(response, "usage_metadata", None)
        usage = _add_usage(usage, extra)
    budget = dict(state.get("budget") or {})
    if usage:
        budget["prompt_tokens"] = budget.get("prompt_tokens", 0) + usage.get("input_tokens", 0)
        budget["completion_tokens"] = budget.get("completion_tokens", 0) + usage.get("output_tokens", 0)
        budget["llm_steps"] = budget.get("llm_steps", 0) + 1
    return {"messages": [response], "budget": budget}


# --------------------------------------------------------------- baseline mode

BASELINE_SYSTEM = """You are an SRE ops agent with every tool available.
Entity names in the task may be informal. If you need a canonical service or
database id, call the lookup_entity tool with a single mention (one call per
mention). Do not guess canonical ids. You MUST call at least one tool before
answering: act now, do not describe what you could do. Answer concisely once
you have enough evidence."""


def _baseline_agent_node(state: AgentState) -> dict:
    llm = _llm().bind_tools(_openai_schemas(_baseline_schemas()))
    messages = [SystemMessage(content=BASELINE_SYSTEM), *state["messages"]]
    response = llm.invoke(messages)
    usage = getattr(response, "usage_metadata", None)
    if not response.tool_calls and not any(isinstance(m, ToolMessage) for m in state["messages"]):
        response = llm.invoke(
            [*messages, response, HumanMessage(content="Do not describe. Call a tool now.")]
        )
        usage = _add_usage(usage, getattr(response, "usage_metadata", None))
    budget = dict(state.get("budget") or {})
    if usage:
        budget["prompt_tokens"] = budget.get("prompt_tokens", 0) + usage.get("input_tokens", 0)
        budget["completion_tokens"] = budget.get("completion_tokens", 0) + usage.get("output_tokens", 0)
        budget["llm_steps"] = budget.get("llm_steps", 0) + 1
    return {"messages": [response], "budget": budget}


def _baseline_lookup_node(store: HydraContextStore) -> Callable:
    """The baseline's entity resolution: one graph round-trip per mention,
    exactly the fan-out the context layer avoids."""
    def node(state: AgentState) -> dict:
        last = state["messages"][-1]
        outs: list[ToolMessage] = []
        resolved: dict = {}
        for call in last.tool_calls:
            if call["name"] != "lookup_entity":
                result = invoke_tool(call["name"], call.get("args", {}))
                outs.append(ToolMessage(content=result, tool_call_id=call["id"]))
                continue
            mention = (call.get("args") or {}).get("mention", "")
            rows = store._run(
                "MATCH (a:Alias)-[:RESOLVES_TO]->(e:Entity) WHERE a.text = $m0 "
                "RETURN e.canonical_name AS name",
                "baseline_lookup_entity",
                m0=mention,
            )
            budget = dict(state.get("budget") or {})
            budget["context_round_trips"] = budget.get("context_round_trips", 0) + 1
            if rows:
                resolved[mention] = rows[0]["name"]
                result = json.dumps({"mention": mention, "canonical": rows[0]["name"]})
            else:
                result = json.dumps({"mention": mention, "canonical": None})
            outs.append(ToolMessage(content=result, tool_call_id=call["id"]))
        return {"messages": outs, "budget": budget}

    return node


# ------------------------------------------------------------------- assembly

def build(store: HydraContextStore, mode: str = "hydra"):
    """Compile the LangGraph agent. mode: "hydra" | "baseline"."""
    counter: dict = {}

    if mode == "hydra":
        def route(state: AgentState):
            return "tools" if state["messages"][-1].tool_calls else END

        g = StateGraph(AgentState)
        g.add_node("load_context", _load_context(store))
        g.add_node("agent", _hydra_agent_node)
        g.add_node("tools", _tools_node(counter))
        g.add_edge(START, "load_context")
        g.add_edge("load_context", "agent")
        g.add_conditional_edges("agent", route, ["tools", END])
        g.add_edge("tools", "agent")
        compiled = g.compile()
    else:
        def route(state: AgentState):
            last = state["messages"][-1]
            if not last.tool_calls:
                return END
            if all(c["name"] == "lookup_entity" for c in last.tool_calls):
                return "resolve"
            return "tools"

        g = StateGraph(AgentState)
        g.add_node("agent", _baseline_agent_node)
        g.add_node("resolve", _baseline_lookup_node(store))
        g.add_node("tools", _tools_node(counter))
        g.add_edge(START, "agent")
        g.add_conditional_edges("agent", route, ["tools", "resolve", END])
        g.add_edge("tools", "agent")
        g.add_edge("resolve", "agent")
        compiled = g.compile()

    compiled._tool_counter = counter  # type: ignore[attr-defined]
    return compiled


def run(store: HydraContextStore, task: str, mode: str = "hydra") -> dict:
    """Run one task and return messages, metrics, and the final answer."""
    import time

    agent = build(store, mode)
    started = time.perf_counter()
    state = agent.invoke(
        {
            "messages": [HumanMessage(content=task)],
            "task": task,
            "pack": {},
            "budget": {},
        },
        {"recursion_limit": MAX_STEPS * 2 + 4},
    )
    wall = round(time.perf_counter() - started, 2)
    budget = dict(state.get("budget") or {})
    budget["wall_seconds"] = wall
    budget["tool_calls"] = agent._tool_counter.get("_count", 0)  # type: ignore[attr-defined]
    final = ""
    for message in reversed(state["messages"]):
        if isinstance(message, AIMessage) and message.content and not message.tool_calls:
            final = message.content if isinstance(message.content, str) else str(message.content)
            break
    used_tools = sorted(
        {c["name"] for m in state["messages"] if isinstance(m, AIMessage) for c in (m.tool_calls or [])}
    )
    return {
        "mode": mode,
        "task": task,
        "final": final,
        "used_tools": used_tools,
        "metrics": budget,
        "steps": len(state["messages"]),
    }


def all_tool_names() -> list[str]:
    return sorted(TOOL_TEMPLATES)
