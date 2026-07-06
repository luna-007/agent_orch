from pydantic import BaseModel
from typing import Any, Protocol
from schemas.agent_schemas import Message

class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]
    
class LLMResponse(BaseModel):
    content: str
    tool_calls: list[ToolCall] | None = None
    
class LLMClient(Protocol):
    async def chat(self, messages: list[Message], tools: list | None = None) -> LLMResponse:
        """"""
