import pytest
import os
import json
from typing import Any
from schemas.tool_schemas import GraphState, Message, AgentOutput
from schemas.llm_schema import LLMResponse, ToolCall, LLMClient
from registry import available_tools
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
        registry=available_tools,
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
        registry=available_tools,
        memory_svc=mock_memory_service,
        config=settings
    )

    saved_messages = []
    def on_save(msg):
        saved_messages.append(msg)

    final_state = await orchestrator.run_turn(state, on_save)

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
    
    import services.search_service
    original_sandbox_root = services.search_service.SANDBOX_ROOT
    services.search_service.SANDBOX_ROOT = os.path.abspath(temp_sandbox_dir)

    try:
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
            registry=available_tools,
            memory_svc=mock_memory_service,
            config=settings
        )

        final_state = await orchestrator.run_turn(state, lambda msg: None)
        assert final_state.current_working_dir == os.path.abspath(subfolder)
    finally:
        services.search_service.SANDBOX_ROOT = original_sandbox_root

@pytest.mark.asyncio
async def test_run_turn_directory_injection(mock_memory_service, temp_sandbox_dir):
    import services.search_service
    original_sandbox_root = services.search_service.SANDBOX_ROOT
    services.search_service.SANDBOX_ROOT = os.path.abspath(temp_sandbox_dir)

    try:
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
            registry=available_tools,
            memory_svc=mock_memory_service,
            config=settings
        )

        final_state = await orchestrator.run_turn(state, lambda msg: None)
        tool_msg = final_state.messages[2]
        assert tool_msg.role == "tool"
        assert "Error" not in tool_msg.content
        assert temp_sandbox_dir in tool_msg.content
    finally:
        services.search_service.SANDBOX_ROOT = original_sandbox_root

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
        registry=available_tools,
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
    orchestrator = Orchestrator(None, None, None, None)

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
