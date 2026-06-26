import requests
import json
from schemas.tool_schemas import Message
from schemas.llm_schema import LLMResponse, LLMClient,  ToolCall
from config import settings

class OllamaClient(LLMClient):
    
    def chat(self, messages: list[Message], tools: list[dict] | None = None) -> LLMResponse:
        
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [msg.model_dump() for msg in messages],
            "think": True,
            "stream": False
        }
        if tools:
            payload["tools"] = tools
            
        response = requests.post(settings.ollama_url, json=payload)
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