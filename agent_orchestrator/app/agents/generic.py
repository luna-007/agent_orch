import json
import logging
from typing import Callable, List, Optional
from mcp import ClientSession
from app.agents.base import Agent
from schemas.agent_schemas import GraphState, AgentOutput
from app.orchestrator import Orchestrator

logger = logging.getLogger("agent_orch.generic_agent")

class GenericAgent(Agent):
    def __init__(
        self,
        name: str,
        system_prompt: str,
        allowed_tools: List[str],
        orchestrator: Orchestrator
    ):
        self._name = name
        self.system_prompt = system_prompt
        self.allowed_tools = allowed_tools
        self.orchestrator = orchestrator

    @property
    def name(self) -> str:
        return self._name

    async def run(
        self,
        state: GraphState,
        on_save: Callable,
        ai_context: Optional[List[AgentOutput]] = None,
        mcp_session: Optional[ClientSession] = None
    ) -> AgentOutput:
        logger.info(f"Agent '{self.name}' starting execution loop.")
        
        # Build memory summary from prior agent runs
        context_summary = ""
        if ai_context:
            context_summary = "\n\nInformation gathered so far by other agents:\n"
            for out in ai_context:
                tools_used = ", ".join(out.tools_called) if out.tools_called else "none"
                context_summary += f"- [{out.state}]: {out.summary} (tools called: {tools_used})\n"

        # Prepend memory summary to the agent's prompt
        full_prompt = self.system_prompt + context_summary

        # Run orchestrator turn scoped to this agent's allowed tools
        updated_state = await self.orchestrator.run_turn(
            state=state,
            on_save=on_save,
            system_prompt=full_prompt,
            allowed_tool_names=self.allowed_tools,
            mcp_session=mcp_session
        )

        last_msg = updated_state.messages[-1].content
        try:
            parsed = json.loads(last_msg)
            agent_out = AgentOutput(**parsed)
        except Exception as e:
            logger.warning(f"Failed to parse AgentOutput JSON from message: {e}. Falling back.")
            agent_out = AgentOutput(
                status="success",
                summary=last_msg,
                state="FINISH",
                reason="Fallback parse",
                tools_called=[]
            )
            
        logger.info(f"Agent '{self.name}' execution completed. Summary: {agent_out.summary[:100]}...")
        return agent_out
