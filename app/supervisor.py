import logging
from typing import Callable, Dict
from app.agents.base import Agent
from app.router import Router
from app.fsm import FSM
from schemas.tool_schemas import GraphState, AgentOutput, Message

logger = logging.getLogger("agent_orch.supervisor")

class Supervisor:
    def __init__(self, agents: Dict[str, Agent], router: Router, fsm: FSM, goal: str = ""):
        self.agents = agents
        self.router = router
        self.fsm = fsm
        self.goal = goal

    async def run_workflow(
        self,
        state: GraphState,
        on_save: Callable,
        strict: bool = True
    ) -> GraphState:
        logger.info(f"Supervisor workflow started for session {state.session_id} with goal: '{state.current_goal}'")
        
        # Keep a backup of original messages before running agents
        original_messages = list(state.messages)
        last_agent_summary = ""
        
        while True:
            # 1. Load accumulated ai_context from graph state
            ai_context_data = state.accumulated_results.get("ai_context", [])
            ai_context = []
            for item in ai_context_data:
                try:
                    ai_context.append(AgentOutput(**item))
                except Exception as e:
                    logger.error(f"Error parsing AgentOutput from accumulated context: {e}")

            # 2. Ask the Router to name the current state based on context
            try:
                decision = await self.router.decide(
                    ai_context=ai_context,
                    current_goal=state.current_goal,
                    valid_states=self.fsm.get_valid_states(),
                    strict=strict
                )
            except Exception as e:
                logger.error(f"Router decision failed: {e}")
                if strict:
                    raise
                else:
                    logger.warning("Failing gracefully to FINISH due to router error in non-strict mode.")
                    break

            logger.info(f"Router selected state: '{decision.current_state}'. Reason: '{decision.reason}'")

            # 3. Look up transition target from FSM transitions
            next_agent_name = self.fsm.get_next_agent(decision.current_state)
            if next_agent_name == "FINISH":
                logger.info("FSM transition target is FINISH. Exiting supervisor workflow.")
                break

            # 4. Find the mapped agent
            agent = self.agents.get(next_agent_name)
            if not agent:
                err_msg = f"Agent '{next_agent_name}' not configured in supervisor."
                logger.error(err_msg)
                raise ValueError(err_msg)

            # Update state with the next step
            state.next_step = next_agent_name

            # 5. Run the target Agent with isolated state.messages and a dummy on_save callback
            logger.info(f"Routing to Agent: '{next_agent_name}'")
            agent_state = GraphState(
                session_id=state.session_id,
                messages=list(original_messages),
                current_working_dir=state.current_working_dir,
                current_goal=state.current_goal,
                accumulated_results=state.accumulated_results,
                next_step=state.next_step
            )
            
            agent_output = await agent.run(agent_state, lambda msg: None, ai_context)
            
            # Sync workspace directory changes
            state.current_working_dir = agent_state.current_working_dir
            
            if agent_output.summary and agent_output.summary.strip():
                last_agent_summary = agent_output.summary
            
            # Map state name automatically if the agent output doesn't match a transition
            if not agent_output.state or agent_output.state == "FINISH":
                if next_agent_name == "researcher":
                    agent_output.state = "RESEARCH_DONE"
                elif next_agent_name == "sys_admin":
                    agent_output.state = "SYS_ADMIN_DONE"
                elif next_agent_name == "summarizer":
                    agent_output.state = "SUMMARIZED"

            logger.info(f"Agent '{next_agent_name}' output state: '{agent_output.state}'")

            # 6. Append the agent output to context memory
            ai_context.append(agent_output)
            state.accumulated_results["ai_context"] = [item.model_dump() for item in ai_context]

        # 7. Clean up messages history: keep only original conversation + the final summary message
        if last_agent_summary:
            final_message = Message(role="assistant", content=last_agent_summary)
            on_save(final_message)
            state.messages = original_messages + [final_message]
        else:
            state.messages = original_messages

        logger.info(f"Supervisor workflow completed for session {state.session_id}")
        return state
