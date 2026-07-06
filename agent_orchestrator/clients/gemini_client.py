import httpx, json
from schemas.agent_schemas import Message
from schemas.llm_schema import LLMClient, ToolCall, LLMResponse
from config import settings
from typing import Any
import logging
import sys

logger = logging.getLogger("agent_orch.gemini_client")
logging.getLogger("httpx").setLevel(logging.WARNING)

class GeminiClient(LLMClient):
    
    async def chat(self, messages: list[Message], tools: list[dict] | None = None) -> LLMResponse:
        headers = {
            "x-goog-api-key": settings.GEMINI_API_KEY or "",
            "Content-Type": "application/json"
        }
        
        # Flatten message history with explicit tool calling context
        conversation_text = ""
        for msg in messages:
            if msg.role == "tool":
                conversation_text += f"tool ({msg.tool_name or 'unknown'}): {msg.content}\n"
            elif msg.role == "assistant" and msg.tool_calls:
                tool_calls_str = ", ".join([
                    f"{tc.get('name') or tc.get('function', {}).get('name')}({tc.get('arguments') or tc.get('function', {}).get('arguments')})" 
                    for tc in msg.tool_calls if isinstance(tc, dict)
                ])
                conversation_text += f"assistant: {msg.content} [Calling tools: {tool_calls_str}]\n"
            else:
                conversation_text += f"{msg.role}: {msg.content}\n"
        
        payload: dict[str, Any] = {
            "model": settings.GEMINI_MODEL,
            "input": conversation_text
        }
        
        if tools:
            google_tools = []
            for tool_schema in tools:
                func_data = tool_schema.get("function", {})
                google_tools.append({
                    "type": "function",
                    "name": func_data.get("name"),
                    "description": func_data.get("description"),
                    "parameters": func_data.get("parameters", {})
                })
            payload["tools"] = google_tools
            
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
        sys.stderr.write(f"\n[DEBUG] Full Tools Payload:\n{json.dumps(payload.get('tools', []), indent=2)}\n")
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(settings.gemini_url, json=payload, headers=headers)
        
        if response.status_code != 200:
            sys.stderr.write(f"\n[Google API Error {response.status_code}]: {response.text}\n")
            return LLMResponse(content=f"API Error: {response.text}", tool_calls=None)
            
        response_data = response.json()
        message_data = ""
        steps = response_data.get("steps", [])
        
        for step in steps:
            if step.get("type") == "model_output":
                content_list = step.get("content", [])
                for part in content_list:
                    if "text" in part:
                        message_data += part["text"]
                        
        raw_tool_calls = response_data.get("tool_calls", [])
        tool_call_list = []
        
        for raw_tool_call in raw_tool_calls:
            func_data = raw_tool_call.get("function", {})
            tool_call_list.append(ToolCall(
                name=func_data.get("name"),
                arguments=func_data.get("arguments", {})
            ))
            
        return LLMResponse(
            content=message_data,
            tool_calls=tool_call_list if tool_call_list else None
        )
