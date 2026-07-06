import httpx
from schemas.agent_schemas import Message
from schemas.llm_schema import LLMResponse, LLMClient, ToolCall
from config import settings
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)

class OllamaClient(LLMClient):
    
    async def chat(self, messages: list[Message], tools: list[dict] | None = None) -> LLMResponse:
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [msg.model_dump() for msg in messages],
            "think": False,
            "stream": False
        }
        if tools:
            payload["tools"] = tools
            
        timeout = httpx.Timeout(
            connect=10.0,    # time to establish connection
            read=120.0,      # time to wait for response
            write=10.0,      # time to send the request
            pool=10.0        # time to acquire a connection from the pool
        )
            
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(settings.ollama_url, json=payload)
            
        if response.status_code != 200:
            import sys
            sys.stderr.write(f"\n[Ollama API Error {response.status_code}]: {response.text}\n")
            return LLMResponse(content=f"Ollama Error: {response.text}", tool_calls=None)

        response_data = response.json()
        message_data = response_data.get("message", {})
        content = message_data.get("content", "")
        raw_tool_calls = message_data.get("tool_calls", [])
        
        tool_call_list = []
        for raw_tool_call in raw_tool_calls:
            func_data = raw_tool_call.get("function", {})
            tool_call_list.append(ToolCall(
                name=func_data.get("name"),
                arguments=func_data.get("arguments", {})
            ))
            
        return LLMResponse(
            content=content,
            tool_calls=tool_call_list if tool_call_list else None
        )
