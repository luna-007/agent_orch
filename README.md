# Agent-Orch

A lightweight, multi-agent, config-driven LLM orchestration framework built from first principles. Agent-Orch exposes the core mechanics of how modern AI agents reason, call tools, route workflows, validate inputs, and chain actions — without the heavy layers of standard commercial frameworks.

The system is decoupled into two core components:
1. **`agent_orchestrator`**: A client-side CLI supervisor that handles session loops, intent classification, and compiles dynamic LangGraph multi-agent state machines.
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

## Features

- **Multi-Agent FSM Routing**: Execution transitions dynamically between specialized sub-agents (`researcher`, `sys_admin`, `summarizer`, `analyzer`, `refactoring_agent`) driven by an LLM-based `Router` naming FSM states and a deterministic Python `FSM` transition engine.
- **Config-Driven Workflows**: Workflows are fully defined in JSON manifests inside `manifests/`, outlining metadata, aliases, scoped agent tool access, FSM transitions, and state decision matrices.
- **Dynamic Multi-Workflow Routing**: Integrates turn-by-turn intent classification, automatically compiling and caching LangGraph supervisors only when the user's intent switches workflows mid-session.
- **Smart Checkpoint Resuming**: Detects new user messages on resumed sessions, resetting FSM states to the router (`START` node) to re-classify and dispatch the new prompt rather than repeating interrupted steps with stale context.
- **SQLite Durable Checkpointing**: Uses SQLite-backed LangGraph checkpointers (`AsyncSqliteSaver` stored in `checkpoints.db`) to persist execution graphs across terminal restarts, allowing users to pause, resume, and review past agent sessions.
- **Robust FSM State Coercion**: Validates agent transitions against manifest-defined states, gracefully coercing invalid or arbitrary outputs to their designated `fallback_state` to prevent infinite loops.
- **Decoupled MCP Architecture**: The supervisor spawns `mcp_server/server.py` as a stdio server subprocess, feeding MCP `ClientSession` streams directly into sub-agent ReAct runs.
- **Ollama Integration & API Compatibility**: Cleanses request payloads of extra schema properties, dynamically transforms `tool_name` references to standard `name` parameters, and enforces lowercase model tagging to prevent registry pulling hangs.
- **Durable Web Fetching & Web Search**: 
  - Upgraded web retrieval using `BeautifulSoup` to parse pages, decomposing scripts, styling, headers, and footers for clean text content.
  - Zero-key Google/DuckDuckGo web searching with redirect URL extraction.
- **Sandboxed Local File Writing**: Allows sub-agents to log outputs or write files under a strict `SANDBOX_ROOT`, blocking path traversal attempts.
- **System Metrics & Inspection**: Gathers OS platforms, dynamic RAM statistics, and system uptime using `psutil`.
- **Clean Chat History Isolation**: Isolates sub-agent ReAct turns by passing copies of conversation history, preventing intermediate JSON thinking steps from polluting user chat history. Saves only the final summaries to SQLite.
- **FSM Context Turn Reset**: Clears FSM memory at the beginning of each user turn so follow-up queries run FSM states from the start instead of locking in the final state.

---

## Project Structure

```text
|
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
├── prompts/
│   └── system_default.txt    # Default system prompt template
├── .env                      # Configuration environment variables
├── ROADMAP_TO_PRODUCTION.md  # Phased development roadmap
└── PRODUCTION_IMPROVEMENTS.md # Dynamic project task tracker
```

---

## How to Add a Tool

**Step 1 — Write the service function**
Create or add your tool logic inside `mcp_server/services/`:
```python
# mcp_server/services/my_service.py
def fetch_data(source: str) -> dict:
    return {"source": source, "data": "..."}
```

**Step 2 — Define Pydantic Input model in `mcp_server/schemas/tool_schemas.py`**
```python
# mcp_server/schemas/tool_schemas.py
class MyToolInput(BaseModel):
    source: str = Field(description="The data source to query")
```

**Step 3 — Register the handler in `mcp_server/server.py`**
Expose the function as an MCP tool using the `@mcp.tool()` decorator:
```python
# mcp_server/server.py
from services.my_service import fetch_data

@mcp.tool()
async def my_tool_handler(query: MyToolInput):
    """Fetches data from a source."""
    raw = fetch_data(query.source)
    return raw
```
*No manual JSON schema files or mapping dictionaries are needed; the MCP Server automatically converts the Pydantic type signatures and handler docstrings into standard MCP tool schemas.*

---

## How to Configure a Workflow

Create or edit a workflow manifest JSON inside `agent_orchestrator/manifests/` (e.g. `agent_orchestrator/manifests/sysadmin_flow.json`). Here is an overview of the schema:

```json
{
  "metadata": {
    "name": "sysadmin_flow",
    "version": "1.0.0",
    "intent": "system_inquiry",
    "goal": "Analyze local filesystem and run system checks",
    "aliases": ["sys", "check", "disk", "files"]
  },
  "agents": {
    "researcher": {
      "description": "Gathers external context or time info.",
      "system_prompt": "You are the Researcher agent. Gather external timezone details.",
      "tools": ["fetch_web_content", "get_time", "web_search"]
    },
    "sys_admin": {
      "description": "Inspects local file systems and system metrics.",
      "system_prompt": "You are the SysAdmin agent. Inspect filesystem configuration.",
      "tools": ["get_disk_usage", "list_directory_contents", "get_system_info"]
    },
    "summarizer": {
      "description": "Compiles all findings.",
      "system_prompt": "You are the Summarizer agent. Compile all findings into a clean report.",
      "tools": []
    }
  },
  "fsm": {
    "transitions": {
      "NEW": "researcher",
      "RESEARCH_DONE": "sys_admin",
      "SYS_ADMIN_DONE": "summarizer",
      "SUMMARIZED": "FINISH"
    },
    "decision_matrix": [
      {"name": "NEW", "description": "Workflow is starting."},
      {"name": "RESEARCH_DONE", "description": "Research completed, ready for system checks."},
      {"name": "SYS_ADMIN_DONE", "description": "System checks completed, ready to summarize."},
      {"name": "SUMMARIZED", "description": "Final summary completed."}
    ]
  }
}
```

---

## Running the CLI Agent

1. Start Ollama:
```bash
ollama serve
```

2. Pull the model defined in your `.env` configuration file:
```bash
ollama pull qwen3.5:4b
```

3. Launch the agent CLI entrypoint:
```bash
python3 agent_orchestrator/main.py
```

---

## Running Tests

Run the client orchestrator/supervisor tests:
```bash
PYTHONPATH=agent_orchestrator python3 -m pytest agent_orchestrator/tests/
```

Run the standalone MCP server tool tests:
```bash
PYTHONPATH=mcp_server python3 -m pytest mcp_server/tests/
```

---

## License

MIT License