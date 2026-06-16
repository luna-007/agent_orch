# Agent Orch

A lightweight agent orchestration framework built from scratch to understand how modern LLM agents perform tool calling, validation, and execution without relying on heavyweight frameworks.

The project connects a locally hosted LLM (via Ollama) with external tools, allowing the model to decide when a tool should be used, execute it safely through validated schemas, and incorporate the results into its final response.

---

## Features

* Tool calling using LLM function definitions
* Dynamic tool registration
* Pydantic-based input validation
* Local LLM support through Ollama
* Extensible tool registry
* Environment-based configuration
* MCP-compatible tool definitions
* Simple orchestration loop for agent execution

---

## Architecture

```text
User Query
     │
     ▼
┌─────────────┐
│   Ollama    │
│     LLM     │
└──────┬──────┘
       │
       │ Tool Request
       ▼
┌─────────────┐
│ Tool Schema │
│ Validation  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Tool Runner │
└──────┬──────┘
       │
       ▼
 Tool Result
       │
       ▼
┌─────────────┐
│     LLM     │
└──────┬──────┘
       │
       ▼
 Final Response
```

---

## Project Structure

```text
agent_orch/
│
├── main.py
├── config.py
├── registry.py
├── tools.py
├── requirements.txt
├── .env
└── README.md
```

### Key Components

| File          | Purpose                         |
| ------------- | ------------------------------- |
| `main.py`     | Agent orchestration loop        |
| `config.py`   | Application configuration       |
| `registry.py` | Tool registration and execution |
| `tools.py`    | Tool implementations            |
| `.env`        | Environment variables           |

---

## Installation

### Clone the repository

```bash
git clone https://github.com/luna-007/agent_orch.git

cd agent_orch
```

### Create a virtual environment

```bash
python -m venv .venv

source .venv/bin/activate
```

Windows:

```powershell
.venv\Scripts\activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

---

## Configure Environment

Create a `.env` file:

```env
MODEL_NAME=qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434
```

Adjust values based on your local setup.

---

## Running Ollama

Start Ollama:

```bash
ollama serve
```

Pull a model:

```bash
ollama pull qwen3:8b
```

Verify:

```bash
ollama list
```

---

## Running the Agent

```bash
python main.py
```

Example interaction:

```text
User: What time is it in Tokyo?

Agent:
The current time in Tokyo is 14:35 JST.
```

The model determines whether a tool is required, executes the tool, and then generates a final response using the returned data.

---

## Creating a New Tool

### 1. Define an input schema

```python
from pydantic import BaseModel

class WeatherInput(BaseModel):
    city: str
```

### 2. Create the tool

```python
@mcp.tool()
def get_weather(city: str):
    return f"Weather for {city}"
```

### 3. Register the tool

```python
available_tools["get_weather"] = {
    "function": get_weather,
    "input_model": WeatherInput,
}
```

The tool becomes available to the agent automatically.

---

## Current Capabilities

* Single-step tool execution
* Tool schema validation
* Dynamic tool discovery
* Local model support
* Extensible architecture

---

## Planned Improvements

### Agent Loop

Enable multiple tool calls within a single interaction.

```text
LLM
 ↓
Tool
 ↓
LLM
 ↓
Tool
 ↓
LLM
 ↓
Answer
```

### Memory

* Conversation memory
* Session persistence
* Long-term memory support

### RAG Integration

* Vector databases
* Document retrieval
* Knowledge grounding

### Observability

* Execution logs
* Tool latency metrics
* Agent traces

### Multi-Agent Support

* Planner agent
* Executor agent
* Critic agent

---

## Why This Project Exists

Most modern agent frameworks abstract away the mechanics of tool calling and orchestration. This project was built to understand those internals from first principles and provide a lightweight foundation for experimenting with:

* Agent architectures
* Tool calling
* MCP integration
* Local LLM deployments
* Autonomous workflows

---

## Tech Stack

* Python
* Ollama
* Pydantic
* MCP
* Local LLMs (Qwen, Llama, Mistral, etc.)

---

## License

MIT License

---

## Author

Rahul

Built as a learning project focused on understanding how modern AI agents reason, call tools, and orchestrate workflows without relying on large agent frameworks.
