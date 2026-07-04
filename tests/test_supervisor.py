import pytest
import json
from typing import List
from schemas.tool_schemas import GraphState, Message, AgentOutput
from schemas.llm_schema import LLMResponse, LLMClient
from registry import ToolRegistry
from app.orchestrator import Orchestrator
from app.agents.generic import GenericAgent
from app.router import Router
from app.fsm import FSM
from app.supervisor import Supervisor

class FakeLLMClient(LLMClient):
    def __init__(self, responses: List[str]):
        # List of string outputs that our LLM will return in sequence
        self.responses = responses
        self.calls = []

    async def chat(self, messages: List[Message], tools: List[dict] | None = None) -> LLMResponse:
        self.calls.append((messages.copy(), tools))
        if self.responses:
            content = self.responses.pop(0)
            return LLMResponse(content=content, tool_calls=None)
        return LLMResponse(content="{}", tool_calls=None)

@pytest.mark.asyncio
async def test_supervisor_workflow_success():
    # Setup LLM responses in order:
    # 1. Router decide (starts NEW)
    # 2. Researcher agent ReAct execution (final JSON output)
    # 3. Router decide (moves to RESEARCH_DONE)
    # 4. SysAdmin agent ReAct execution (final JSON output)
    # 5. Router decide (moves to SYS_ADMIN_DONE)
    # 6. Summarizer agent execution (final JSON output)
    # 7. Router decide (moves to SUMMARIZED)
    llm_responses = [
        # 1. Router decide (state NEW)
        '{"current_state": "NEW", "reason": "Beginning workflow"}',
        # 2. Researcher agent
        '{"status": "success", "summary": "Time is 10:00 AM", "state": "RESEARCH_DONE", "reason": "Research complete", "tools_called": []}',
        # 3. Router decide (state RESEARCH_DONE)
        '{"current_state": "RESEARCH_DONE", "reason": "Researcher finished"}',
        # 4. SysAdmin agent
        '{"status": "success", "summary": "Disk space is 50%", "state": "SYS_ADMIN_DONE", "reason": "Checked systems", "tools_called": []}',
        # 5. Router decide (state SYS_ADMIN_DONE)
        '{"current_state": "SYS_ADMIN_DONE", "reason": "SysAdmin finished"}',
        # 6. Summarizer agent
        '{"status": "success", "summary": "Summary: Time is 10AM, Disk space is 50%", "state": "SUMMARIZED", "reason": "Compiled report", "tools_called": []}',
        # 7. Router decide (state SUMMARIZED)
        '{"current_state": "SUMMARIZED", "reason": "Workflow completed"}'
    ]
    
    llm = FakeLLMClient(llm_responses)
    
    # Simple setup
    registry = ToolRegistry({})
    orchestrator = Orchestrator(llm, registry, None, None)
    
    router = Router(llm)
    
    transitions = {
        "NEW": "researcher",
        "RESEARCH_DONE": "sys_admin",
        "SYS_ADMIN_DONE": "summarizer",
        "SUMMARIZED": "FINISH"
    }
    
    decision_matrix = [
        {"name": "NEW", "description": "Start"},
        {"name": "RESEARCH_DONE", "description": "Research completed"},
        {"name": "SYS_ADMIN_DONE", "description": "Sys admin completed"},
        {"name": "SUMMARIZED", "description": "Summarization completed"}
    ]
    
    fsm = FSM(transitions, decision_matrix)
    
    researcher = GenericAgent("researcher", "research prompt", [], orchestrator)
    sys_admin = GenericAgent("sys_admin", "sys admin prompt", [], orchestrator)
    summarizer = GenericAgent("summarizer", "summarizer prompt", [], orchestrator)
    
    agents = {
        "researcher": researcher,
        "sys_admin": sys_admin,
        "summarizer": summarizer
    }
    
    supervisor = Supervisor(agents, router, fsm)
    
    state = GraphState(
        session_id="test_workflow_session",
        messages=[],
        current_goal="Inspect time and system disk space",
        accumulated_results={}
    )
    
    def on_save(msg):
        pass

    final_state = await supervisor.run_workflow(state, on_save, strict=True)
    
    # The supervisor should have updated state.accumulated_results["ai_context"]
    ai_context_data = final_state.accumulated_results.get("ai_context", [])
    assert len(ai_context_data) == 3
    assert ai_context_data[0]["state"] == "RESEARCH_DONE"
    assert ai_context_data[1]["state"] == "SYS_ADMIN_DONE"
    assert ai_context_data[2]["state"] == "SUMMARIZED"
    assert "Summary: Time is 10AM" in ai_context_data[2]["summary"]

@pytest.mark.asyncio
async def test_supervisor_router_strict_validation():
    # Router returns an invalid FSM state
    llm = FakeLLMClient([
        '{"current_state": "INVALID_STATE", "reason": "Hallucination"}'
    ])
    
    registry = ToolRegistry({})
    orchestrator = Orchestrator(llm, registry, None, None)
    router = Router(llm)
    fsm = FSM({}, [{"name": "NEW", "description": "Start"}])
    
    supervisor = Supervisor({}, router, fsm)
    state = GraphState(
        session_id="test_session",
        messages=[],
        current_goal="Goal",
        accumulated_results={}
    )
    
    # In strict mode, it should raise ValueError
    with pytest.raises(ValueError) as exc:
        await supervisor.run_workflow(state, lambda m: None, strict=True)
    assert "invalid FSM state 'INVALID_STATE'" in str(exc.value)

    # In non-strict mode, it should warn and terminate with FINISH
    llm_non_strict = FakeLLMClient([
        '{"current_state": "INVALID_STATE", "reason": "Hallucination"}'
    ])
    router_non_strict = Router(llm_non_strict)
    supervisor_non_strict = Supervisor({}, router_non_strict, fsm)
    
    final_state = await supervisor_non_strict.run_workflow(state, lambda m: None, strict=False)
    # Exited safely without exception
    assert "ai_context" not in final_state.accumulated_results or len(final_state.accumulated_results["ai_context"]) == 0
