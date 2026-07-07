import httpx
from schemas.agent_schemas import Message
from schemas.llm_schema import LLMResponse, LLMClient, ToolCall
from config import settings
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("agent_orch.ollama_client")

class OllamaClient(LLMClient):
    
    async def chat(self, messages: list[Message], tools: list[dict] | None = None) -> LLMResponse:
        formatted_messages = []
        for msg in messages:
            content = msg.content or ""
            # Escape XML special characters to prevent Ollama template/parser failures on raw text
            if content:
                content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                
            msg_dict = {
                "role": msg.role,
                "content": content
            }
            if msg.role == "tool":
                msg_dict["name"] = msg.tool_name or ""
            elif msg.role == "assistant" and msg.tool_calls:
                ollama_tool_calls = []
                for tc in msg.tool_calls:
                    tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                    tc_args = tc.get("arguments") if isinstance(tc, dict) else getattr(tc, "arguments", {})
                    ollama_tool_calls.append({
                        "type": "function",
                        "function": {
                            "name": tc_name,
                            "arguments": tc_args
                        }
                    })
                msg_dict["tool_calls"] = ollama_tool_calls
            formatted_messages.append(msg_dict)

        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": formatted_messages,
            "options": {
                "temperature": 0.0,
                "num_ctx": 16384,
                "num_predict": 2048
            },
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
            raise RuntimeError(f"Ollama API returned status {response.status_code}: {response.text}")

        response_data = response.json()
        message_data = response_data.get("message", {})
        content = message_data.get("content", "")
        raw_tool_calls = message_data.get("tool_calls", [])
        
        logger.debug(f"Ollama payload tools count: {len(tools) if tools else 0}")
        logger.debug(f"Ollama response tool_calls: {raw_tool_calls}")
        if tools and not raw_tool_calls:
            logger.warning(f"LLM did not invoke any tools despite {len(tools)} tools being available.")
        
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
