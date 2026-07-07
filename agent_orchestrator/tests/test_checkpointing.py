import pytest
import os
from typing import List
from schemas.agent_schemas import GraphState, Message, AgentOutput
from schemas.llm_schema import LLMResponse, LLMClient
from app.orchestrator import Orchestrator
from app.agents.generic import GenericAgent
from app.router import Router
from app.fsm import FSM
from app.supervisor import Supervisor
from config import settings

class FakeLLMClient(LLMClient):
    def __init__(self, responses: List[str]):
        self.responses = responses
        self.calls = []

    async def chat(self, messages: List[Message], tools: List[dict] | None = None) -> LLMResponse:
        self.calls.append((messages.copy(), tools))
        if self.responses:
            content = self.responses.pop(0)
            return LLMResponse(content=content, tool_calls=None)
        return LLMResponse(content="{}", tool_calls=None)

class FailableAgent(GenericAgent):
    def __init__(self, name: str, system_prompt: str, allowed_tools: list, orchestrator: Orchestrator, should_fail: bool = False):
        super().__init__(name, system_prompt, allowed_tools, orchestrator)
        self.should_fail = should_fail

    async def run(self, state: GraphState, on_save: callable, ai_context: list = None, mcp_session=None) -> AgentOutput:
        if self.should_fail:
            raise RuntimeError("Simulated agent execution failure")
        return await super().run(state, on_save, ai_context, mcp_session=mcp_session)

@pytest.mark.asyncio
async def test_workflow_checkpointing_and_resume(tmp_path):
    # Set a custom checkpoint DB path for isolation during tests
    db_file = str(tmp_path / "test_checkpoints.db")
    settings.CHECKPOINT_DATABASE_PATH = db_file

    llm_responses_run1 = [
        '{"current_state": "NEW", "reason": "Beginning workflow"}'
    ]
    
    llm1 = FakeLLMClient(llm_responses_run1)
    orchestrator1 = Orchestrator(llm1, None, None)
    router1 = Router(llm1)
    
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
    
    # Configure researcher to fail on Run 1
    researcher1 = FailableAgent("researcher", "research prompt", [], orchestrator1, should_fail=True)
    agents1 = {"researcher": researcher1}
    supervisor1 = Supervisor(agents1, router1, fsm)
    
    state = GraphState(
        session_id="test_session_resume_456",
        messages=[],
        current_goal="Goal",
        accumulated_results={}
    )
    
    # Run 1 should fail with RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        await supervisor1.run_workflow(state, lambda m: None, strict=True)
    assert "Simulated agent execution failure" in str(exc_info.value)
    
    # Run 2: Resume with healthy agents
    # Router fast-path uses agent states directly, so no router LLM calls needed
    llm_responses_run2 = [
        # Researcher runs successfully:
        '{"status": "success", "summary": "Info: 10AM", "state": "RESEARCH_DONE", "reason": "Success", "tools_called": []}',
        # SysAdmin runs successfully:
        '{"status": "success", "summary": "Disk: 40%", "state": "SYS_ADMIN_DONE", "reason": "Success", "tools_called": []}',
        # Summarizer runs successfully:
        '{"status": "success", "summary": "Final report", "state": "SUMMARIZED", "reason": "Success", "tools_called": []}'
    ]
    
    llm2 = FakeLLMClient(llm_responses_run2)
    orchestrator2 = Orchestrator(llm2, None, None)
    router2 = Router(llm2)
    
    researcher2 = FailableAgent("researcher", "research prompt", [], orchestrator2, should_fail=False)
    sys_admin = GenericAgent("sys_admin", "sys admin prompt", [], orchestrator2)
    summarizer = GenericAgent("summarizer", "summarizer prompt", [], orchestrator2)
    
    agents2 = {
        "researcher": researcher2,
        "sys_admin": sys_admin,
        "summarizer": summarizer
    }
    
    supervisor2 = Supervisor(agents2, router2, fsm)
    
    # We pass the same state containing the session_id to resume from the last successful checkpoint
    final_state = await supervisor2.run_workflow(state, lambda m: None, strict=True)
    
    ai_context_data = final_state.accumulated_results.get("ai_context", [])
    assert len(ai_context_data) == 3
    assert ai_context_data[0]["state"] == "RESEARCH_DONE"
    assert ai_context_data[1]["state"] == "SYS_ADMIN_DONE"
    assert ai_context_data[2]["state"] == "SUMMARIZED"
    assert ai_context_data[2]["summary"] == "Final report"

@pytest.mark.asyncio
async def test_multi_turn_session_reset(tmp_path):
    db_file = str(tmp_path / "test_checkpoints_multi.db")
    settings.CHECKPOINT_DATABASE_PATH = db_file

    # First turn LLM responses (only initial router call uses LLM, rest use fast-path)
    llm_responses_turn1 = [
        '{"current_state": "NEW", "reason": "Beginning turn 1"}',
        '{"status": "success", "summary": "Turn 1 Research", "state": "RESEARCH_DONE", "reason": "Success", "tools_called": []}',
        '{"status": "success", "summary": "Turn 1 SysAdmin", "state": "SYS_ADMIN_DONE", "reason": "Success", "tools_called": []}',
        '{"status": "success", "summary": "Turn 1 final report", "state": "SUMMARIZED", "reason": "Success", "tools_called": []}'
    ]
    
    llm1 = FakeLLMClient(llm_responses_turn1)
    orchestrator1 = Orchestrator(llm1, None, None)
    router1 = Router(llm1)
    
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
    
    researcher1 = GenericAgent("researcher", "research prompt", [], orchestrator1)
    sys_admin1 = GenericAgent("sys_admin", "sys admin prompt", [], orchestrator1)
    summarizer1 = GenericAgent("summarizer", "summarizer prompt", [], orchestrator1)
    
    agents = {
        "researcher": researcher1,
        "sys_admin": sys_admin1,
        "summarizer": summarizer1
    }
    
    supervisor = Supervisor(agents, router1, fsm)
    
    state = GraphState(
        session_id="multi_turn_test_session_789",
        messages=[Message(role="user", content="Turn 1 query")],
        current_goal="Goal",
        accumulated_results={}
    )
    
    # Run Turn 1
    final_state1 = await supervisor.run_workflow(state, lambda m: None, strict=True)
    assert "Turn 1 final report" in final_state1.messages[-1].content
    
    # Second turn LLM responses (same thread ID, initial router uses LLM, rest fast-path)
    llm_responses_turn2 = [
        '{"current_state": "NEW", "reason": "Beginning turn 2"}',
        '{"status": "success", "summary": "Turn 2 Research", "state": "RESEARCH_DONE", "reason": "Success", "tools_called": []}',
        '{"status": "success", "summary": "Turn 2 SysAdmin", "state": "SYS_ADMIN_DONE", "reason": "Success", "tools_called": []}',
        '{"status": "success", "summary": "Turn 2 final report", "state": "SUMMARIZED", "reason": "Success", "tools_called": []}'
    ]
    
    llm2 = FakeLLMClient(llm_responses_turn2)
    orchestrator2 = Orchestrator(llm2, None, None)
    router2 = Router(llm2)
    
    researcher2 = GenericAgent("researcher", "research prompt", [], orchestrator2)
    sys_admin2 = GenericAgent("sys_admin", "sys admin prompt", [], orchestrator2)
    summarizer2 = GenericAgent("summarizer", "summarizer prompt", [], orchestrator2)
    
    agents2 = {
        "researcher": researcher2,
        "sys_admin": sys_admin2,
        "summarizer": summarizer2
    }
    
    supervisor2 = Supervisor(agents2, router2, fsm)
    
    # Update messages in state for turn 2 (simulating main loop appending user message)
    final_state1.messages.append(Message(role="user", content="Turn 2 query"))
    
    # Run Turn 2 on the same session ID
    final_state2 = await supervisor2.run_workflow(final_state1, lambda m: None, strict=True)
    assert "Turn 2 final report" in final_state2.messages[-1].content

