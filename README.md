# Agent-Orch

A lightweight, multi-agent, config-driven LLM orchestration framework built from first principles. Agent-Orch exposes the core mechanics of how modern AI agents reason, call tools, route workflows, validate inputs, and chain actions — without the heavy layers of standard commercial frameworks.

It runs against a **local Ollama model** or **Google Gemini** and supports two modes: an interactive CLI supervisor agent and a Model Context Protocol (MCP) server.

---

## Architecture Overview

```text
             ┌──────────────── CLI / MCP entrypoints ────────────────┐
             │            python3 main.py / registry.py               │
             └───────────────────────────┬────────────────────────────┘
                                         ▼
                         ┌───────── Intent Classifier ─────────┐
                         │ Matches request to workflow intent  │
                         └───────────────┬─────────────────────┘
                                         ▼
                         ┌───────── Workflow Builder ──────────┐
                         │ Reads JSON manifest → builds:       │
                         │ 1. FSM (Transition Engine)          │
                         │ 2. Router (LLM selects state)       │
                         │ 3. Supervisor (Hub-and-spoke loop)  │
                         └───────────────┬─────────────────────┘
                                         ▼
                         ┌─────────── Supervisor ──────────────┐
                         │ Orchestrates state transitions &    │
                         │ runs sub-agents with clean history  │
                         └───────────────┬─────────────────────┘
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
- **SQLite Durable Checkpointing**: Uses SQLite-backed LangGraph checkpointers to persist execution graphs across terminal restarts, allowing users to pause, resume, and review past agent sessions.
- **Robust FSM State Coercion**: Validates agent transitions against manifest-defined states, gracefully coercing invalid or arbitrary outputs to their designated `fallback_state` to prevent infinite loops.
- **Schema-Less Tool Registry**: Automatically generates OpenAPI/JSON-RPC tool schemas at boot time using Pydantic's `model_json_schema()` and docstrings, eliminating manual JSON schema configuration drift.
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
agent_orch/
├── main.py                  # CLI entrypoint, session loop, intent classification
├── registry.py              # Tool registry, dynamic schema builder, MCP server
├── cli.py                   # Terminal session database manager
├── config.py                # Pydantic BaseSettings, startup validation, logging setup
├── ROADMAP_TO_PRODUCTION.md # Phased evolution path (ignored from git)
│
├── app/
│   ├── agents/
│   │   ├── base.py          # Abstract Agent definition
│   │   └── generic.py       # Concrete GenericAgent with orchestrator loop
│   ├── fsm.py               # Transition map validation engine
│   ├── intent_classifier.py # LLM-based query-to-workflow classifier
│   ├── manifest_schema.py   # jsonschema validator for workflow manifests
│   ├── orchestrator.py      # ReAct loop, sandbox parameters injection, schema checks
│   ├── prompt_manager.py    # Loads system templates from prompts/
│   ├── router.py            # LLM router deciding next FSM state
│   └── supervisor.py        # Hub-and-spoke supervisor running isolated workflows
│
├── manifests/
│   ├── sysadmin_flow.json   # Sysadmin agent FSM workflow manifest
│   └── new_flow.json        # Python code refactoring workflow manifest
│
├── prompts/
│   └── system_default.txt   # Core agent instruction template
│
├── schemas/
│   ├── llm_schema.py        # LLMClient Protocol & response structures
│   └── tool_schemas.py      # Pydantic input models (DTOs) for all tools
│
├── services/
│   ├── ai_services.py       # Generates session titles
│   ├── disk_service.py      # Disk space inspection
│   ├── memory_service.py    # SQLite WAL database session manager
│   ├── search_service.py    # Sandboxed directory list, file read & file write
│   ├── system_service.py    # System platform & RAM statistics
│   ├── time_service.py      # Case-insensitive robust timezone time service
│   └── web_service.py       # BeautifulSoup web fetcher and web searcher
│
└── tests/                   # 14-test suite for tools, schemas, and workflows
```

---

## How to Add a Tool

**Step 1 — Write the service function**
```python
# services/my_service.py
def fetch_data(source: str) -> dict:
    return {"source": source, "data": "..."}
```

**Step 2 — Define Pydantic Input model in schemas/tool_schemas.py**
```python
# schemas/tool_schemas.py
class MyToolInput(BaseModel):
    source: str = Field(description="The data source to query")
```

**Step 3 — Register the handler in registry.py**
```python
# registry.py
@mcp.tool()
async def my_tool_handler(query: MyToolInput):
    """Fetches data from a source."""
    raw = fetch_data(query.source)
    return raw
```

**Step 4 — Add to available_tools**
```python
# registry.py (inside available_tools dict)
"my_tool": {
    "func": my_tool_handler,
    "input_model": MyToolInput,
    "schema": generate_tool_schema("my_tool", my_tool_handler.__doc__, MyToolInput)
}
```
*No JSON schema files are needed; the system generates schemas automatically from the Pydantic type signatures and handler docstrings.*

---

## How to Configure a Workflow

Create or edit a workflow manifest JSON inside `manifests/` (e.g. `manifests/sysadmin_flow.json`). Here is an overview of the schema:

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

Start Ollama:
```bash
ollama serve
```

Pull a model:
```bash
ollama pull qwen2.5-coder:7b-instruct-q3_K_M
```

Launch the agent:
```bash
python3 main.py
```

---

## Running Tests

Run the test suite to verify tool execution, FSM router state changes, and manifest parsing validation:
```bash
python3 -m pytest tests/
```

---

## License

MIT License