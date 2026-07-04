import pytest
import os
import tempfile
from services.web_service import fetch_web_content, search_web
from services.search_service import write_local_file
from services.system_service import get_system_info

@pytest.mark.asyncio
async def test_fetch_web_content_error():
    # Attempting to fetch an invalid domain should fail gracefully and return the error message
    res = await fetch_web_content("http://invalid.domain.xyz")
    assert res["title"] == "Error"
    assert "Failed to fetch content" in res["content"]

@pytest.mark.asyncio
async def test_web_search_success():
    # Search should return a list of dictionary results
    res = await search_web("test search query", max_results=2)
    assert isinstance(res, list)
    if len(res) > 0 and "error" not in res[0]:
        assert "url" in res[0]
        assert "title" in res[0]
        assert "snippet" in res[0]

def test_write_local_file_sandbox():
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_file = "test_sandbox_file.txt"
    test_content = "Hello sandbox test!"
    
    # 1. Success case inside sandbox
    res = write_local_file(current_dir, test_file, test_content)
    assert res["status"] == "success"
    
    full_path = res["file_path"]
    assert os.path.exists(full_path)
    
    with open(full_path, "r", encoding="utf-8") as f:
        assert f.read() == test_content
        
    # Cleanup
    os.remove(full_path)
    
    # 2. PermissionError when escaping sandbox root
    with pytest.raises(PermissionError):
        write_local_file(current_dir, "../../../escaped_sandbox_file.txt", "escape")

def test_system_info():
    info = get_system_info()
    assert isinstance(info, dict)
    assert "system" in info
    assert "cpu_count" in info
    assert "memory_total_gb" in info
    assert "uptime_seconds" in info
    assert info["cpu_count"] > 0
    assert info["memory_total_gb"] > 0.0

def test_parse_thinking_blocks():
    from app.orchestrator import Orchestrator
    from app.router import Router, RouterDecision
    from schemas.llm_schema import LLMClient, LLMResponse
    from schemas.tool_schemas import AgentOutput
    from registry import available_tools

    class DummyLLM(LLMClient):
        async def chat(self, messages, tools=None):
            return LLMResponse(content="dummy", tool_calls=None)

    llm = DummyLLM()
    orchestrator = Orchestrator(llm, available_tools, None, None)
    
    dirty_text = """<think>
    Let's think about this. It's a test.
    </think>
    {
        "status": "success",
        "summary": "Agent successfully parsed",
        "state": "FINISH",
        "reason": "Successfully filtered thinking tags",
        "tools_called": []
    }"""
    
    parsed = orchestrator.parse_agent_output(dirty_text, [])
    assert parsed.status == "success"
    assert parsed.summary == "Agent successfully parsed"
    assert parsed.state == "FINISH"

    # Test Router decision parsing with thinking blocks
    router = Router(llm)
    dirty_router_text = """Some prefix thought process
    </think>
    {
        "current_state": "RESEARCH_DONE",
        "reason": "Thinking tag was parsed"
    }"""
    decision = router._parse_decision(dirty_router_text)
    assert decision.current_state == "RESEARCH_DONE"
    assert decision.reason == "Thinking tag was parsed"
