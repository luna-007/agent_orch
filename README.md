# Agent Orch

A lightweight, modular agent orchestration framework built from scratch to understand how modern LLM agents perform tool calling, validation, and execution without relying on heavyweight frameworks.

The project connects a locally hosted LLM (via Ollama) with local system utilities and external web APIs. It supports two execution modes:

* Running as an autonomous, interactive command-line agent.
* Acting as a standardized MCP (Model Context Protocol) server integrated with developer tools like Claude Code and Cursor.

---

## Features

### Fully Autonomous ReAct Loop

Enables the agent to evaluate prompts, decide on a sequence of tool calls, execute them, analyze the outcomes, and dynamically chain additional tools without human intervention.

### Separation of Concerns (Controller-Service Pattern)

Strictly isolates low-level operating system and network actions (**Services**) from API schema validation and data mapping (**Controllers**).

### Dual Pydantic Validation

Uses Pydantic v2 models as Input and Output DTOs (Data Transfer Objects) to guarantee type safety on both incoming LLM arguments and outgoing Python execution results.

### Native MCP Server Support

Fully compatible with the Model Context Protocol (`mcp==2.0.0a1`), running over standard input/output (stdio) transport for seamless integration with modern developer environments.

### Centralized Configuration

Parses and validates `.env` parameters using a dedicated settings class to keep environment configuration separate from application logic.

### Robust Input Sanitization

Implements defensive coding practices, such as case-insensitive timezone normalization, to prevent non-deterministic LLM outputs from causing runtime failures.

---

# Architecture

The project supports two execution pathways:

1. Direct execution through the interactive CLI agent.
2. Integration with external MCP clients such as Claude Code or Cursor.

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
                              │ (Schema Handshake & Execution)
                              ▼
                ┌──────────────────────────┐
                │  registry.py (Controller)│ <--- @mcp.tool()
                │  Pydantic DTO Validation │
                └─────────────┬────────────┘
                              │ (Clean Python Call)
                              ▼
                ┌──────────────────────────┐
                │     services/ (Logic)    │
                │ shutil, datetime, requests│
                └──────────────────────────┘
```

---

# Project Structure

```text
agent_orch/
│
├── config.py              # Environment configuration loader
├── registry.py            # MCP Server & unified tool execution mapping
├── main.py                # Interactive multi-turn Agent orchestrator
│
├── schemas/
│   ├── __init__.py
│   └── tool_schemas.py    # Pydantic models (Message, Input/Output DTOs)
│
├── services/
│   ├── __init__.py
│   ├── disk_service.py    # Directory and disk utility service
│   ├── time_service.py    # Timezone and clock utility service
│   └── web_service.py     # Web scraping and HTML sanitization service
│
├── .env
└── README.md
```

---

# Key Components

| Component     | Purpose                                                                                   |
| ------------- | ----------------------------------------------------------------------------------------- |
| `main.py`     | Handles the interactive CLI and recursive ReAct orchestration loop.                       |
| `config.py`   | Centralized configuration management using validated settings.                            |
| `registry.py` | Controller layer containing MCP tool definitions, validation, and stdio server execution. |
| `schemas/`    | Data layer containing Pydantic DTOs and conversation state models.                        |
| `services/`   | Business logic layer containing isolated system and web utilities.                        |

---

# Installation

## 1. Clone the Repository

```bash
git clone https://github.com/luna-007/agent_orch.git
cd agent_orch
```

## 2. Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b-instruct-q3_K_M
```

> **Note:** Claude Code adds a substantial system prompt. Running a 7B–8B model with a 3-bit quantization is recommended when operating on hardware with approximately 6GB VRAM.

---

# Running the Agent Locally

Ensure Ollama is running and your target model has been downloaded:

```bash
ollama serve
ollama pull qwen2.5-coder:7b-instruct-q3_K_M
```

Start the agent:

```bash
python3 main.py
```

### Example Interaction

```text
you:
List my project's root directory to find where my schemas folder is,
list that schemas folder to find the file name,
and then search inside that file for the word 'Message'.

[Executing Tool: list_directory_contents] for '.'
[Executing Tool: list_directory_contents] for 'schemas'
[Executing Tool: search_local_files] for 'Message'

[AI Final Answer]
I found the schemas directory and identified the file
'tool_schemas.py'. The term 'Message' is defined on line 15.
```

---

# Integrating with Claude Code

Because Agent Orch exposes tools through the MCP protocol, it can be registered directly with Claude Code.

## 1. Register the MCP Server

Use the absolute path to your project:

```bash
claude mcp add system-monitor -- python3 /absolute/path/to/agent_orch/registry.py
```

## 2. Configure Claude Code

Export the following variables before launching Claude:

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

## 3. Launch Claude

```bash
claude
```

Claude can now execute your local MCP tools through standard I/O communication.

---

# Creating a New Tool

Agent Orch follows a simple three-layer pattern:

## 1. Create the Service Layer

Inside `services/`:

```python
def fetch_data_utility(url: str):
    return {
        "url": url,
        "data": "value"
    }
```

---

## 2. Define Pydantic DTOs

Inside `schemas/tool_schemas.py`:

```python
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    url: str = Field(description="The target URL")

class MyToolOutput(BaseModel):
    url: str
    data: str
```

---

## 3. Create the Controller

Inside `registry.py`:

```python
@mcp.tool()
def fetch_data_handler(query: MyToolInput) -> str:
    """Fetch data from a URL."""

    raw_data = fetch_data_utility(url=query.url)

    validated = MyToolOutput(**raw_data)

    return validated.data
```

Once registered, the tool becomes available to:

* The interactive ReAct agent (`main.py`)
* Any connected MCP client

---

# Planned Improvements

### Persistent Database Memory

Store conversation history in SQLite to support resumable sessions and long-term memory.

### Dockerization

Package the MCP server inside a lightweight Docker image to ensure consistent execution environments.

### Just-In-Time RAG Web Reader

Implement dynamic chunking and retrieval using vector databases such as ChromaDB or LanceDB, allowing large webpages to be processed efficiently while minimizing context usage.

---

# Why This Project Exists

Most modern agent frameworks abstract away the mechanics of tool calling, validation, orchestration, and execution.

Agent Orch intentionally takes the opposite approach.

The goal is to understand how agent systems work beneath the abstraction layer by implementing the core building blocks directly:

* Tool registration
* Schema validation
* ReAct-style reasoning loops
* MCP protocol integration
* Service orchestration
* Local LLM execution

It is designed primarily as a learning project and experimentation platform rather than a production framework.

---

# License

MIT License

---

# Author

**Rahul Kumar**

Built to explore how modern AI agents reason, call tools, and orchestrate workflows from first principles.
