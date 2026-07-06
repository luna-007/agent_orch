import pytest
import os
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
