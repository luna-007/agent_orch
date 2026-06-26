from pydantic import BaseModel, Field
from typing import Any, Protocol, Optional
from schemas.tool_schemas import Message

class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]
    
class LLMResponse(BaseModel):
    content: str
    tool_calls: list[ToolCall] | None = None
    
class LLMClient(Protocol):
    
    def chat(self, messages: list[Message], tools: list | None = None) -> LLMResponse:
        """"""