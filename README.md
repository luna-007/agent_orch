# Agent-Orch

A lightweight agent orchestration framework built from scratch to understand how modern LLM agents reason, call tools, validate inputs, and execute actions without relying on heavyweight abstractions.

Unlike frameworks such as LangChain, CrewAI, or AutoGen, Agent-Orch intentionally exposes the underlying mechanics of agent systems. It combines a local LLM (via Ollama), strongly typed tool interfaces, and MCP server compatibility into a minimal codebase designed for learning, experimentation, and extension.

The project can run either as:

* An autonomous command-line agent with a recursive ReAct loop
* A Model Context Protocol (MCP) server that integrates with clients such as Claude Code and Cursor

---

## Why This Project Exists

Modern agent frameworks make it easy to build AI applications, but they often hide the details that make agents work:

* How tool calling actually happens
* How inputs and outputs are validated
* How reasoning loops are orchestrated
* How external tools are exposed to language models
* How protocols such as MCP connect models to real-world capabilities

Agent-Orch was built to explore these concepts from first principles.

Every major component, from the orchestration loop to tool registration and schema validation, is intentionally visible and easy to understand. Rather than abstracting away the core mechanics, the project exposes them in a clean, modular architecture that can be inspected, modified, and extended.

The result is a compact but complete framework that demonstrates the building blocks behind modern AI agents while remaining practical enough to support real-world experimentation.

---

## Features

### Fully Autonomous ReAct Loop

Enables the agent to:

* Analyze user requests
* Select appropriate tools
* Execute tool calls
* Evaluate outcomes
* Dynamically chain additional tools when needed

without requiring human intervention during execution.

### Separation of Concerns (Controller-Service Pattern)

Strictly separates:

* Controllers: Validation, schema handling, and tool registration
* Services: Operating system interactions, web requests, and business logic

This keeps the codebase maintainable and easy to extend.

### Dual Pydantic Validation

Uses Pydantic v2 DTOs for:

* LLM input validation
* Tool output validation

ensuring type safety across the entire execution pipeline.

### Native MCP Server Support

Runs as a fully compliant MCP server using `mcp==2.0.0a1`, enabling seamless integration with:

* Claude Code
* Cursor
* Any MCP-compatible client

### Centralized Configuration

Environment variables are parsed and validated through a dedicated settings layer, keeping configuration concerns separate from application logic.

### Robust Input Sanitization

Defensive normalization and validation help prevent malformed LLM outputs from causing runtime failures.

---

## Architecture

This project supports two execution pathways:

1. Direct execution through the interactive CLI agent
2. Integration through external MCP clients

```text
    [ Interactive Terminal ]                          [ Claude CLI / Cursor ]
              │                                                 │
              │ (Direct Run)                                    │ (Local STDIO Pipe)
              ▼                                                 ▼
┌────────────────────────────┐                        ┌───────────────────┐
│     main.py (Client)       │                        │    MCP Client     │
│  Stateful Conversation     │                        └─────────┬─────────┘
│  & Recursive ReAct Loop    │                                  │
└─────────────┬──────────────┘                                  │
              │                                                 │
              └───────────────┬─────────────────────────────────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │ registry.py (Controller) │
                │  Pydantic Validation     │
                └─────────────┬────────────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │     services/ (Logic)    │
                │ System & Network Actions │
                └──────────────────────────┘
```

---

## Project Structure

```text
agent_orch/
│
├── config.py
├── registry.py
├── main.py
│
├── schemas/
│   ├── __init__.py
│   └── tool_schemas.py
│
├── services/
│   ├── __init__.py
│   ├── disk_service.py
│   ├── time_service.py
│   └── web_service.py
│
├── .env
└── README.md
```

### Key Components

| Component     | Purpose                                                |
| ------------- | ------------------------------------------------------ |
| `main.py`     | Interactive CLI and recursive ReAct orchestration loop |
| `registry.py` | MCP server, validation layer, and tool registration    |
| `config.py`   | Centralized configuration management                   |
| `schemas/`    | Pydantic DTOs and conversation state models            |
| `services/`   | Isolated business logic and utility functions          |

---

## Installation

### Clone the Repository

```bash
git clone https://github.com/luna-007/agent_orch.git
cd agent_orch
```

### Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment Variables

Create a `.env` file in the project root:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b-instruct-q3_K_M
```

> Claude Code introduces a significant system prompt overhead. For machines with limited VRAM (around 6GB), a 7B–8B model using 3-bit quantization is generally recommended.

---

## Running the Agent Locally

Start Ollama:

```bash
ollama serve
```

Pull your preferred model:

```bash
ollama pull qwen2.5-coder:7b-instruct-q3_K_M
```

Launch the agent:

```bash
python3 main.py
```

### Example

```text
you:
List my project's root directory to find where my schemas folder is,
list that schemas folder to find the file name,
and then search inside that file for the word 'Message'.

[Executing Tool: list_directory_contents]
[Executing Tool: list_directory_contents]
[Executing Tool: search_local_files]

[AI Final Answer]
I found the schemas directory and identified the file
'tool_schemas.py'. The term 'Message' is defined on line 15.
```

---

## Integrating with Claude Code

### Register the MCP Server

```bash
claude mcp add system-monitor -- python3 /absolute/path/to/agent_orch/registry.py
```

### Configure Claude Code

```bash
export ANTHROPIC_BASE_URL="http://localhost:11434"
export ANTHROPIC_API_KEY="ollama"
export ANTHROPIC_AUTH_TOKEN="ollama"

export ANTHROPIC_MODEL="qwen2.5-coder:7b-instruct-q3_K_M"

export ANTHROPIC_DEFAULT_SONNET_MODEL="qwen2.5-coder:7b-instruct-q3_K_M"
export ANTHROPIC_DEFAULT_OPUS_MODEL="qwen2.5-coder:7b-instruct-q3_K_M"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="qwen2.5-coder:7b-instruct-q3_K_M"

export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1"
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=4096
export CLAUDE_CODE_DISABLE_THINKING="1"
```

### Launch Claude

```bash
claude
```

Claude can now access and execute your locally exposed MCP tools.

---

## Creating a New Tool

### Step 1: Create the Service

```python
def fetch_data_utility(url: str):
    return {
        "url": url,
        "data": "value"
    }
```

### Step 2: Define DTOs

```python
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    url: str = Field(description="The target URL")

class MyToolOutput(BaseModel):
    url: str
    data: str
```

### Step 3: Register the Tool

```python
@mcp.tool()
def fetch_data_handler(query: MyToolInput) -> str:
    raw_data = fetch_data_utility(url=query.url)

    validated = MyToolOutput(**raw_data)

    return validated.data
```

The tool immediately becomes available to both the local agent and connected MCP clients.

---

## Planned Improvements

### Persistent Database Memory

Move conversation history into SQLite and support resumable sessions via a unique `session_id`.

### Dockerization

Package the MCP server inside a lightweight Docker image to ensure reproducible deployments.

### Just-In-Time RAG Web Reader

Implement chunking and retrieval using ChromaDB or LanceDB to efficiently process large webpages while minimizing context consumption.

---

## License

MIT License

---

## Author

**Rahul Kumar**

Built as a learning project focused on understanding how modern AI agents reason, call tools, and orchestrate workflows from first principles.
