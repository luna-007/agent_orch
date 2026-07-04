from typing import Callable

from schemas.tool_schemas import GraphState, Message
from schemas.llm_schema import LLMClient
from app.orchestrator import Orchestrator
from registry import available_tools


async def run_sys_admin_agent(state: GraphState, llm: LLMClient, on_save: Callable) -> GraphState:
    
    sys_admin_tool_keys = [""]
    
    
    
    
    
async def run_researcher_agent(state: GraphState, llm: LLMClient, on_save: Callable) -> GraphState:
    
