from typing import Literal, Optional, Any, Annotated
from pydantic import BaseModel, Field
import os

class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = Field(
        description="The role being used"
    )
    content: str
    tool_name: Optional[str] = None
    tool_calls: Optional[list] = None

def reduce_messages(left: list, right: list) -> list:
    if not isinstance(left, list):
        left = [left]
    if not isinstance(right, list):
        right = [right]
    # Simple message consolidation
    return left + right

class GraphState(BaseModel):
    session_id: str
    messages: Annotated[list[Message], reduce_messages]
    current_working_dir: str = Field(
        default_factory=lambda: os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    current_goal: str
    accumulated_results: dict[str, Any] = Field(default_factory=dict)
    next_step: str | None = None

class AgentOutput(BaseModel):
    status: Literal["success", "error", "partial"] = Field(description="The status of the agent run")
    summary: str = Field(description="The summary of actions taken and final answer")
    state: str = Field(description="The target state for the workflow FSM")
    reason: str = Field(default="", description="The reasoning behind selecting the state and final answer")
    tools_called: list[str] = Field(default_factory=list, description="A list of tools used during execution")
