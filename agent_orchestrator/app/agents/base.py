from abc import ABC, abstractmethod
from typing import Callable, List, Optional
from mcp import ClientSession
from schemas.agent_schemas import GraphState, AgentOutput

class Agent(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """The identifier of the agent."""
        pass

    @abstractmethod
    async def run(
        self,
        state: GraphState,
        on_save: Callable,
        ai_context: Optional[List[AgentOutput]] = None,
        mcp_session: Optional[ClientSession] = None
    ) -> AgentOutput:
        """Run the agent's logic on the state and return its output."""
        pass
