# Agent-Orch

A lightweight, multi-agent, config-driven LLM orchestration framework built from first principles. Agent-Orch exposes the core mechanics of how modern AI agents reason, call tools, route workflows, validate inputs, and chain actions — without the heavy layers of standard commercial frameworks.

The system is decoupled into two core components:
1. **`agent_orchestrator`**: A client-side CLI supervisor that handles session loops, intent classification, and compiles dynamic multi-agent state machines.
2. **`mcp_server`**: A standalone Model Context Protocol (MCP) server running as a subprocess to dynamically serve tools and execute actions under a stdio session.

---

## Architecture Overview

```text
             ┌───────────── CLI Entrypoint ─────────────┐
             │      agent_orchestrator/main.py          │
             └───────────────────┬──────────────────────┘
                                 ▼
                 ┌─────── Intent Classifier ───────┐
                 │ Matches query to workflow intent│
                 └───────────────┬─────────────────┘
                                 ▼
                 ┌─────── Workflow Builder ────────┐
                 │ Reads JSON manifest → builds:   │
                 │ 1. FSM (Transition Engine)      │
                 │ 2. Router (LLM selects state)   │
                 │ 3. Supervisor (Hub-and-spoke)   │
                 └───────────────┬─────────────────┘
                                 ▼
                 ┌────────── Supervisor ───────────┐
                 │ Spawns MCP Server subprocess &  │
                 │ runs LangGraph workflow loops   │
                 └───────────────┬─────────────────┘
                                 │ (via stdio client)
                                 ▼
                 ┌─────────── MCP Server ───────────┐
                 │       mcp_server/server.py       │
                 └───────────────┬──────────────────┘
                                 │
                   ┌─────────────┴─────────────┐
                   ▼                           ▼
       ┌── Sub-agent (ReAct) ──┐   ...×N agents...
       │   Orchestrator loop   │
       └───────────┬───────────┘
                   ▼
       Tools (dynamic Pydantic schemas)
```

---

## Key Core Framework Mechanics

### 1. Config-Driven Workflows & FSM Transitions
Workflows are defined fully in JSON manifests under `agent_orchestrator/manifests/`. They define metadata, intent aliases, sub-agent configurations (system prompts, tool access restrictions), and a finite state machine (FSM) schema containing transition mapping and state descriptions.
- **FSM State Coercion:** Handled programmatically via `agent_orchestrator/app/fsm.py` which validates LLM transition outputs and coerces arbitrary values to designated `fallback_state` targets to prevent infinite routing loops.

### 2. Intelligent Routing & Intent Classification
- **Dynamic Multi-Workflow Routing:** Turn-by-turn intent classification matches user queries to workflow manifests, dynamically compiling and caching the correct state machine.
- **Programmatic Router Constraints:** The FSM state router programmatically limits available transition targets (e.g. enforcing initial state constraints like `NEW` or `RESEARCH_DONE` on empty histories) without relying on heavy system prompt guardrails.

### 3. Hybrid Tool Executor (Concurrent & Sequential)
To optimize performance and enforce environment safety, the execution engine (`agent_orchestrator/app/orchestrator.py`) handles tools based on their scope:
- **Concurrent Execution:** Network-bound or stateless tools (e.g., timezone checks, web searches, page scraping) run concurrently via `asyncio.gather` for low-latency response cycles.
- **Sequential Execution:** Stateful local filesystem and system tools (e.g., reading/writing files, changing directories) execute sequentially to prevent race conditions or stdio stream corruption.

### 4. Smart Checkpoint & SQLite State Persistence
- **LangGraph Checkpoint Resuming:** Employs SQLite-backed state persistence (`checkpoints.db`) to preserve execution graphs.
- **Turn-Based Clean Resets:** Clears accumulated FSM context variables (`ai_context`) at the start of new user turns, allowing resumed sessions to start from the router (`START` node) rather than re-executing stale steps.

### 5. Context Pruning & Narrative History Cleansing
Prevents LLM token bloat and bias by filtering intermediate JSON tool calls and raw outputs from the history.
- **Reasoning Retention:** Compiles previous turns' raw assistant tool calls and responses into a clean, human-readable textual narrative (e.g., summarizing reasoning and tools executed) for subsequent model context.

### 6. Multi-LLM Clients with API-Specific Optimizations
- **Gemini Client (`gemini_client.py`):** Configured for native `/v1beta/interactions` endpoint. Includes custom parsing to sequentially resolve `function_call` steps from the response `steps` block.
- **Ollama Client (`ollama_client.py`):** Configured with XML tag-mismatch prevention. Sets a large `num_ctx` (16,384 tokens) and `num_predict` (2,048 tokens) to prevent prompt truncation, and escapes special XML-like characters (`<`, `>`, `&`) in message payloads so Qwen model handlers parse tool calls reliably.
- **Tool Schema Catch-22 Exclusion:** Programmatically removes the required `current_dir` property from tool definitions passed to LLMs, resolving the schema constraint issue for directory-relative tools while injecting the client-managed current directory value behind the scenes.

---

## Directory Structure

```text
.
├── agent_orchestrator/       # CLI multi-agent orchestrator application (Client)
│   ├── main.py               # CLI entrypoint, session loop, intent classification
│   ├── cli.py                # Terminal session database manager
│   ├── config.py             # Pydantic Settings and logging setup
│   │
│   ├── app/
│   │   ├── agents/
│   │   │   ├── base.py       # Abstract Agent definition
│   │   │   └── generic.py    # Concrete GenericAgent with orchestrator loop
│   │   ├── fsm.py            # FSM transition validation engine
│   │   ├── intent_classifier.py # LLM intent classifier
│   │   ├── manifest_schema.py   # jsonschema manifest validator
│   │   ├── orchestrator.py   # ReAct loop, MCP tool call execution client
│   │   ├── prompt_manager.py # Loads system prompt templates
│   │   ├── router.py         # LLM FSM state router
│   │   └── supervisor.py     # Hub-and-spoke supervisor running isolated workflows
│   │
│   ├── clients/
│   │   ├── gemini_client.py  # Gemini LLM client implementation
│   │   └── ollama_client.py  # Ollama LLM client implementation
│   │
│   ├── manifests/
│   │   ├── sysadmin_flow.json # System inquiry workflow manifest
│   │   └── new_flow.json      # Code refactoring workflow manifest
│   │
│   ├── schemas/
│   │   └── agent_schemas.py  # GraphState, AgentOutput, Message schemas
│   │
│   ├── services/
│   │   └── memory_service.py # SQLite database memory manager
│   │
│   └── tests/                # Test suite for orchestrator, supervisor, and FSM
│
├── mcp_server/               # Standalone MCP Server exposing tools (Server)
│   ├── server.py             # MCPServer initialization and tool registrations
│   │
│   ├── schemas/
│   │   └── tool_schemas.py   # Pydantic input models (DTOs) for all tools
│   │
│   ├── services/
│   │   ├── disk_service.py   # Disk space inspection
│   │   ├── search_service.py # Filesystem sandboxed list, read & write
│   │   ├── system_service.py # System platform & memory statistics
│   │   ├── time_service.py   # Robust timezone time service
│   │   └── web_service.py    # BeautifulSoup web content scraper and searcher
│   │
│   └── tests/                # Unit tests for MCP server tools
│
├── .env                      # Configuration environment variables
├── ROADMAP_TO_PRODUCTION.md  # Phased development roadmap
└── PRODUCTION_IMPROVEMENTS.md # Dynamic project task tracker
```

---

## Getting Started

### 1. Prerequisites
- **Python**: Version 3.10 or higher.
- **Ollama** (if running locally): Install from [ollama.com](https://ollama.com).

### 2. Configure Environment variables
Create a `.env` file in the root directory:
```env
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="qwen3.5:4B"

GEMINI_BASE_URL="https://generativelanguage.googleapis.com"
GEMINI_MODEL="gemini-2.5-flash"
GEMINI_API_KEY="your-gemini-api-key"
```

### 3. Run the CLI Application
Launch the terminal supervisor:
```bash
python3 agent_orchestrator/main.py
```

---

## Adding Custom Tools & Workflows

### How to Add a Tool
1. **Write the Service Logic:** Create your tool logic function inside `mcp_server/services/`.
2. **Define input schema:** Declare a Pydantic `BaseModel` DTO in `mcp_server/schemas/tool_schemas.py`.
3. **Register the handler:** Open `mcp_server/server.py` and register the function with `@mcp.tool()`:
   ```python
   from services.my_service import my_func
   from schemas.tool_schemas import MyFuncSchema

   @mcp.tool()
   async def my_tool(query: MyFuncSchema):
       """Short description explaining what the tool does."""
       return my_func(query.param)
   ```

### How to Configure a Workflow
Create a new manifest JSON inside `agent_orchestrator/manifests/` defining the state machine states, transitions, agent tools access scope, and fallback routing matrix.

---

## Running Tests

Run client orchestrator/supervisor tests:
```bash
PYTHONPATH=agent_orchestrator python3 -m pytest agent_orchestrator/tests/
```

Run standalone MCP server tool tests:
```bash
PYTHONPATH=mcp_server python3 -m pytest mcp_server/tests/
```

---

## License
MIT License