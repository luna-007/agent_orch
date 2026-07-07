import pytest
import os
import json
from typing import Any
from schemas.agent_schemas import GraphState, Message, AgentOutput
from schemas.llm_schema import LLMResponse, ToolCall, LLMClient
from app.orchestrator import Orchestrator
from config import settings

class FakeLLMClient(LLMClient):
    def __init__(self, responses: list[LLMResponse]):
        self.responses = responses
        self.calls = []

    async def chat(self, messages: list[Message], tools: list[dict] | None = None) -> LLMResponse:
        self.calls.append((messages.copy(), tools))
        if self.responses:
            return self.responses.pop(0)
        return LLMResponse(content="Default fake response", tool_calls=None)

# Mock classes for MCP ClientSession
class MockTool:
    def __init__(self, name: str, description: str, input_schema: dict):
        self.name = name
        self.description = description
        self.input_schema = input_schema

class MockListToolsResult:
    def __init__(self, tools: list):
        self.tools = tools

class MockContentItem:
    def __init__(self, text: str):
        self.text = text

class MockCallToolResult:
    def __init__(self, content: list):
        self.content = content

class MockClientSession:
    def __init__(self, tools: list, tool_responses: dict | None = None):
        self.tools = tools
        self.tool_responses = tool_responses or {}
        self.initialized = False

    async def initialize(self):
        self.initialized = True

    async def list_tools(self):
        return MockListToolsResult(self.tools)

    async def call_tool(self, name: str, arguments: dict):
        resp = self.tool_responses.get(name, "Mock output")
        if callable(resp):
            resp = resp(arguments)
        return MockCallToolResult([MockContentItem(str(resp))])

@pytest.fixture
def temp_sandbox_dir(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    return str(sandbox)

@pytest.fixture
def mock_memory_service():
    class MockMemoryService:
        def __init__(self):
            self.saved_messages = []
        def save_message_to_db(self, session_id: str, message: Message):
            self.saved_messages.append((session_id, message))
    return MockMemoryService()

@pytest.mark.asyncio
async def test_run_turn_no_tools(mock_memory_service, temp_sandbox_dir):
    state = GraphState(
        session_id="test_session",
        messages=[Message(role="user", content="Hello")],
        current_working_dir=temp_sandbox_dir,
        current_goal="Test Orchestrator",
        accumulated_results={}
    )

    llm = FakeLLMClient([
        LLMResponse(content="Hello! How can I help you?", tool_calls=None)
    ])
    
    orchestrator = Orchestrator(
        llm=llm,
        memory_svc=mock_memory_service,
        config=settings
    )

    saved_messages = []
    def on_save(msg):
        saved_messages.append(msg)

    final_state = await orchestrator.run_turn(state, on_save)

    assert len(final_state.messages) == 2
    assert final_state.messages[-1].role == "assistant"
    
    # Content should be JSON representing AgentOutput fallback
    parsed = json.loads(final_state.messages[-1].content)
    assert parsed["summary"] == "Hello! How can I help you?"
    assert parsed["status"] == "success"
    assert parsed["state"] == "FINISH"
    assert len(saved_messages) == 1

@pytest.mark.asyncio
async def test_run_turn_with_tool_call(mock_memory_service, temp_sandbox_dir):
    state = GraphState(
        session_id="test_session",
        messages=[Message(role="user", content="Check space")],
        current_working_dir=temp_sandbox_dir,
        current_goal="Test tool usage",
        accumulated_results={}
    )

    llm = FakeLLMClient([
        LLMResponse(
            content="",
            tool_calls=[ToolCall(name="get_disk_usage", arguments={"type": "Total"})]
        ),
        LLMResponse(
            content="Your total disk space looks great.",
            tool_calls=None
        )
    ])

    orchestrator = Orchestrator(
        llm=llm,
        memory_svc=mock_memory_service,
        config=settings
    )

    # Prepare Mock MCP ClientSession
    tools = [
        MockTool("get_disk_usage", "Fetch disk usage", {"properties": {"type": {"type": "string"}}})
    ]
    session = MockClientSession(tools, {"get_disk_usage": "250 Gb"})

    saved_messages = []
    def on_save(msg):
        saved_messages.append(msg)

    final_state = await orchestrator.run_turn(state, on_save, mcp_session=session)

    assert len(final_state.messages) == 4
    assert final_state.messages[1].role == "assistant"
    assert len(final_state.messages[1].tool_calls) == 1
    assert final_state.messages[2].role == "tool"
    assert final_state.messages[3].role == "assistant"
    
    parsed = json.loads(final_state.messages[3].content)
    assert parsed["summary"] == "Your total disk space looks great."
    assert parsed["tools_called"] == ["get_disk_usage"]

@pytest.mark.asyncio
async def test_run_turn_change_directory(mock_memory_service, temp_sandbox_dir):
    subfolder = os.path.join(temp_sandbox_dir, "sub")
    os.makedirs(subfolder, exist_ok=True)
    
    state = GraphState(
        session_id="test_session",
        messages=[Message(role="user", content="Go to sub")],
        current_working_dir=temp_sandbox_dir,
        current_goal="Navigate folder",
        accumulated_results={}
    )

    llm = FakeLLMClient([
        LLMResponse(
            content="",
            tool_calls=[ToolCall(name="change_directory", arguments={"path": "sub"})]
        ),
        LLMResponse(
            content="I have moved directories.",
            tool_calls=None
        )
    ])

    orchestrator = Orchestrator(
        llm=llm,
        memory_svc=mock_memory_service,
        config=settings
    )

    tools = [
        MockTool("change_directory", "Change dir", {"properties": {"path": {"type": "string"}}})
    ]
    session = MockClientSession(tools, {"change_directory": "Directory changed"})

    final_state = await orchestrator.run_turn(state, lambda msg: None, mcp_session=session)
    assert final_state.current_working_dir == os.path.abspath(subfolder)

@pytest.mark.asyncio
async def test_run_turn_directory_injection(mock_memory_service, temp_sandbox_dir):
    state = GraphState(
        session_id="test_session",
        messages=[Message(role="user", content="Where am I?")],
        current_working_dir=temp_sandbox_dir,
        current_goal="Verify current folder",
        accumulated_results={}
    )

    llm = FakeLLMClient([
        LLMResponse(
            content="",
            tool_calls=[ToolCall(name="get_current_directory", arguments={})]
        ),
        LLMResponse(
            content="You are in the sandbox folder.",
            tool_calls=None
        )
    ])

    orchestrator = Orchestrator(
        llm=llm,
        memory_svc=mock_memory_service,
        config=settings
    )

    tools = [
        MockTool("get_current_directory", "Get current dir", {"properties": {"current_dir": {"type": "string"}}})
    ]
    session = MockClientSession(tools, {"get_current_directory": lambda args: args.get("current_dir", "")})

    final_state = await orchestrator.run_turn(state, lambda msg: None, mcp_session=session)
    tool_msg = final_state.messages[2]
    assert tool_msg.role == "tool"
    assert "Error" not in tool_msg.content
    assert temp_sandbox_dir in tool_msg.content

@pytest.mark.asyncio
async def test_system_prompt_passing(mock_memory_service, temp_sandbox_dir):
    state = GraphState(
        session_id="test_session",
        messages=[Message(role="user", content="Hello")],
        current_working_dir=temp_sandbox_dir,
        current_goal="Goal",
        accumulated_results={}
    )

    llm = FakeLLMClient([
        LLMResponse(content="Hi!", tool_calls=None)
    ])
    
    orchestrator = Orchestrator(
        llm=llm,
        memory_svc=mock_memory_service,
        config=settings
    )

    await orchestrator.run_turn(state, lambda m: None, system_prompt="System instructions here")
    
    # Verify the first call's messages had the system prompt
    assert len(llm.calls) == 1
    messages_sent, _ = llm.calls[0]
    assert messages_sent[0].role == "system"
    assert messages_sent[0].content == "System instructions here"
    assert messages_sent[1].role == "user"

def test_three_tier_parsing():
    orchestrator = Orchestrator(None, None, None)

    # Tier 1: Strict JSON
    t1_json = '{"status": "success", "summary": "Strict parsed", "state": "FINISH", "reason": "reasoning"}'
    out1 = orchestrator.parse_agent_output(t1_json, ["t1"])
    assert out1.summary == "Strict parsed"
    assert out1.tools_called == ["t1"]

    # Tier 2: Markdown block
    t2_md = 'Here is the response:\n```json\n{"status": "success", "summary": "Markdown parsed", "state": "FINISH"}\n```'
    out2 = orchestrator.parse_agent_output(t2_md, ["t2"])
    assert out2.summary == "Markdown parsed"
    assert out2.tools_called == ["t2"]

    # Tier 3: Loose regex
    t3_loose = 'Greeting user { "status": "partial", "summary": "Loose regex parsed", "state": "NEXT_STATE" } farewell'
    out3 = orchestrator.parse_agent_output(t3_loose, ["t3"])
    assert out3.status == "partial"
    assert out3.summary == "Loose regex parsed"
    assert out3.state == "NEXT_STATE"

    # Fallback
    t4_fallback = "A direct text response that does not contain JSON structure."
    out4 = orchestrator.parse_agent_output(t4_fallback, ["t4"])
    assert out4.status == "success"
    assert out4.summary == "A direct text response that does not contain JSON structure."
    assert out4.state == "FINISH"
    assert out4.reason == "Fallback parsed from unstructured text"
    assert out4.tools_called == ["t4"]

def test_schema_flattening_and_wrapping():
    orchestrator = Orchestrator(None, None, None)

    # 1. Test flattening of $defs ref
    schema_defs = {
        "properties": {
            "query": {
                "$ref": "#/$defs/DiskQueryInput"
            }
        },
        "required": ["query"],
        "type": "object",
        "$defs": {
            "DiskQueryInput": {
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["Total", "Used", "Free"]
                    }
                },
                "required": ["type"],
                "type": "object"
            }
        }
    }
    flat_defs = orchestrator._flatten_tool_schema(schema_defs)
    assert flat_defs["properties"]["type"]["type"] == "string"
    assert flat_defs["properties"]["type"]["enum"] == ["Total", "Used", "Free"]
    assert "query" not in flat_defs["properties"]
    assert flat_defs["required"] == ["type"]

    # 2. Test flattening of definitions ref
    schema_definitions = {
        "properties": {
            "query": {
                "$ref": "#/definitions/DiskQueryInput"
            }
        },
        "required": ["query"],
        "type": "object",
        "definitions": {
            "DiskQueryInput": {
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["Total"]
                    }
                },
                "required": ["type"],
                "type": "object"
            }
        }
    }
    flat_definitions = orchestrator._flatten_tool_schema(schema_definitions)
    assert flat_definitions["properties"]["type"]["type"] == "string"
    assert flat_definitions["properties"]["type"]["enum"] == ["Total"]
    assert flat_definitions["required"] == ["type"]

    # 3. Test flattening of inline properties
    schema_inline = {
        "properties": {
            "query": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["Free"]
                    }
                },
                "required": ["type"]
            }
        },
        "required": ["query"],
        "type": "object"
    }
    flat_inline = orchestrator._flatten_tool_schema(schema_inline)
    assert flat_inline["properties"]["type"]["type"] == "string"
    assert flat_inline["properties"]["type"]["enum"] == ["Free"]
    assert flat_inline["required"] == ["type"]

@pytest.mark.asyncio
async def test_history_cleaning_preserves_metadata(mock_memory_service, temp_sandbox_dir):
    state = GraphState(
        session_id="test_session",
        messages=[
            Message(role="user", content="Turn 1 Query"),
            Message(role="assistant", content="", tool_calls=[ToolCall(name="get_system_info", arguments={})]),
            Message(role="tool", tool_name="get_system_info", content="some system details"),
            Message(
                role="assistant",
                content=json.dumps({
                    "status": "success",
                    "summary": "This is a summary of turn 1.",
                    "state": "FINISH",
                    "reason": "I ran get_system_info to check OS.",
                    "tools_called": ["get_system_info"]
                })
            ),
            Message(role="user", content="Turn 2 Query")
        ],
        current_working_dir=temp_sandbox_dir,
        current_goal="Goal",
        accumulated_results={}
    )

    llm = FakeLLMClient([
        LLMResponse(content="I see the details.", tool_calls=None)
    ])
    
    orchestrator = Orchestrator(
        llm=llm,
        memory_svc=mock_memory_service,
        config=settings
    )

    await orchestrator.run_turn(state, lambda m: None)
    
    assert len(llm.calls) == 1
    messages_sent, _ = llm.calls[0]
    
    # Message 0: Turn 1 Query (user)
    # Message 1: Cleaned Turn 1 Response (assistant)
    # Message 2: Turn 2 Query (user)
    assert len(messages_sent) == 3
    
    assistant_msg = messages_sent[1]
    assert assistant_msg.role == "assistant"
    assert "Summary of response: This is a summary of turn 1." in assistant_msg.content
    assert "Reasoning/Context: I ran get_system_info to check OS." in assistant_msg.content
    assert "Tools executed in this turn: get_system_info" in assistant_msg.content


