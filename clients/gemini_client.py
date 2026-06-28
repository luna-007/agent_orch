import httpx, os, json
from schemas.tool_schemas import Message
from schemas.llm_schema import LLMClient, ToolCall, LLMResponse
from config import settings
from dotenv import load_dotenv
from typing import Any
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)

load_dotenv()

class GeminiClient(LLMClient):
    
    async def chat(self, messages: list[Message], tools: list[dict] | None = None) -> LLMResponse:
        
        headers = {
        "x-goog-api-key": os.getenv("GEMINI_API_KEY", ""),
        "Content-Type": "application/json"
        }
        
        conversation_text = ""
        for msg in messages:
            conversation_text += f"{msg.role}: {msg.content}\n"
        
        payload: dict[str,Any] = {
            "model": settings.GEMINI_MODEL,
            "input": conversation_text
        }
        if tools:
            google_tools = []
            for tool_schema in tools:
                # Extract the nested "function" dictionary
                func_data = tool_schema.get("function", {})
                
                # Rebuild it dynamically into Google's native flat format!
                google_tools.append({
                    "type": "function",
                    "name": func_data.get("name"),
                    "description": func_data.get("description"),
                    "parameters": func_data.get("parameters", {})
                })
                
            payload["tools"] = google_tools
            
        timeout = httpx.Timeout(
        connect=10.0,    # time to establish connection
        read=120.0,      # time to wait for response — this is what's failing
        write=10.0,      # time to send the request
        pool=10.0        # time to acquire a connection from the pool
        )
        
        import sys
        sys.stderr.write(f"\n[DEBUG] Full Tools Payload:\n{json.dumps(payload.get('tools', []), indent=2)}\n")
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(settings.gemini_url, json=payload, headers=headers)
        
        response_data = response.json()
        
        if response.status_code != 200:
            import sys
            # Write Google's raw error explaining what is wrong with the payload
            sys.stderr.write(f"\n[Google API Error {response.status_code}]: {response.text}\n")
            return LLMResponse(content=f"API Error: {response.text}", tool_calls=None)
        
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
            arguments=func_data.get("arguments", {})))
            
        return LLMResponse(
        content=message_data,
        tool_calls=tool_call_list if tool_call_list else None
        )
        