import logging
import os
from typing import Callable, Dict
from collections.abc import Hashable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.agents.base import Agent
from app.router import Router
from app.fsm import FSM
from schemas.agent_schemas import GraphState, AgentOutput, Message
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from config import settings

logger = logging.getLogger("agent_orch.supervisor")

class Supervisor:
    def __init__(
        self,
        agents: Dict[str, Agent],
        router: Router,
        fsm: FSM,
        goal: str = "",
        fallback_states: Dict[str, str] | None = None
    ):
        self.agents = agents
        self.router = router
        self.fsm = fsm
        self.goal = goal
        self.fallback_states = fallback_states or {}
        
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(GraphState)

        # Register decision router node
        workflow.add_node("router", self._router_node)

        # Add nodes for each registered agent dynamically
        for agent_name, agent in self.agents.items():
            workflow.add_node(agent_name, self._create_agent_node(agent_name, agent))

        # Set entrypoint edge
        workflow.add_edge(START, "router")

        # Routing decision logic based on current next_step state
        def route_decision(state: GraphState):
            if state.next_step == "FINISH" or not state.next_step:
                return "FINISH"
            return state.next_step

        path_map: Dict[Hashable, str] = {
            agent_name: agent_name for agent_name in self.agents.keys()
        }
        path_map["FINISH"] = END

        workflow.add_conditional_edges(
            "router",
            route_decision,
            path_map=path_map
        )

        # Add direct edges from each agent node back to the router
        for agent_name in self.agents.keys():
            workflow.add_edge(agent_name, "router")

        return workflow

    async def _router_node(self, state: GraphState, config: RunnableConfig):
        # 1. Load accumulated ai_context from graph state
        ai_context_data = state.accumulated_results.get("ai_context", [])
        ai_context = []
        for item in ai_context_data:
            try:
                ai_context.append(AgentOutput(**item))
            except Exception as e:
                logger.error(f"Error parsing AgentOutput from accumulated context: {e}")

        strict = config.get("configurable", {}).get("strict", True)

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
                return {"next_step": "FINISH"}

        logger.info(f"Router selected state: '{decision.current_state}'. Reason: '{decision.reason}'")

        # 3. Look up transition target from FSM transitions
        next_agent_name = self.fsm.get_next_agent(decision.current_state)
        
        return {"next_step": next_agent_name}

    def _create_agent_node(self, agent_name: str, agent: Agent):
        async def agent_node(state: GraphState, config: RunnableConfig):
            logger.info(f"Routing to Agent: '{agent_name}'")
            
            on_save = config.get("configurable", {}).get("on_save", lambda msg: None)
            mcp_session = config.get("configurable", {}).get("mcp_session")
            
            # Build memory summary from prior agent runs
            ai_context_data = state.accumulated_results.get("ai_context", [])
            ai_context = []
            for item in ai_context_data:
                try:
                    ai_context.append(AgentOutput(**item))
                except Exception as e:
                    logger.error(f"Error parsing AgentOutput from context: {e}")

            # Run the target Agent with isolated state.messages
            agent_state = GraphState(
                session_id=state.session_id,
                messages=list(state.messages),
                current_working_dir=state.current_working_dir,
                current_goal=state.current_goal,
                accumulated_results=state.accumulated_results,
                next_step=state.next_step
            )
            
            agent_output = await agent.run(agent_state, on_save, ai_context, mcp_session=mcp_session)
            
            # Sync workspace directory changes
            current_working_dir = agent_state.current_working_dir
            
            # Map state name automatically if the agent output doesn't match a transition or is invalid
            valid_states = set(self.fsm.transitions.keys()) | set(self.fsm.transitions.values())
            if not agent_output.state or agent_output.state == "FINISH" or agent_output.state not in valid_states:
                fallback = self.fallback_states.get(agent_name)
                if fallback:
                    agent_output.state = fallback
            
            logger.info(f"Agent '{agent_name}' output state: '{agent_output.state}'")
            
            # Append the agent output to context memory
            ai_context.append(agent_output)
            accumulated_results = dict(state.accumulated_results)
            accumulated_results["ai_context"] = [item.model_dump() for item in ai_context]
            
            if agent_output.summary and agent_output.summary.strip():
                accumulated_results["last_agent_summary"] = agent_output.summary
                
            return {
                "current_working_dir": current_working_dir,
                "accumulated_results": accumulated_results,
                "messages": agent_state.messages[len(state.messages):]
            }
        return agent_node

    async def run_workflow(
        self,
        state: GraphState,
        on_save: Callable,
        strict: bool = True
    ) -> GraphState:
        logger.info(f"Supervisor workflow started for session {state.session_id} with goal: '{state.current_goal}'")
        
        checkpoint_db = settings.CHECKPOINT_DATABASE_PATH
        
        # Build path to decoupled mcp_server/server.py
        workspace_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        server_path = os.path.join(workspace_dir, "mcp_server", "server.py")
        
        server_params = StdioServerParameters(
            command="python3",
            args=[server_path],
            env={
                **os.environ,
                "OLLAMA_BASE_URL": settings.OLLAMA_BASE_URL,
                "OLLAMA_MODEL": settings.OLLAMA_MODEL,
                "GEMINI_BASE_URL": settings.GEMINI_BASE_URL,
                "GEMINI_MODEL": settings.GEMINI_MODEL,
                "GEMINI_API_KEY": settings.GEMINI_API_KEY or ""
            }
        )
        
        try:
            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    
                    async with AsyncSqliteSaver.from_conn_string(checkpoint_db) as memory:
                        # Compile graph with checkpointing
                        compiled_graph = self._graph.compile(checkpointer=memory)
                        
                        config: RunnableConfig = {
                            "configurable": {
                                "thread_id": state.session_id,
                                "on_save": on_save,
                                "strict": strict,
                                "mcp_session": session
                            }
                        }
                        
                        # Check if there is an existing checkpoint for this thread_id to resume from
                        state_info = await compiled_graph.aget_state(config)
                        if state_info and state_info.values:
                            checkpoint_msgs = state_info.values.get("messages", [])
                            # If the previous turn completed, OR if the user sent a new message, we reset to the router.
                            if not state_info.next or len(state.messages) > len(checkpoint_msgs):
                                logger.info(f"New turn or session restart detected for session {state.session_id}. Resetting graph state to router.")
                                await compiled_graph.aupdate_state(
                                    config,
                                    {
                                        "messages": state.messages,
                                        "accumulated_results": state.accumulated_results,
                                        "next_step": "NEW"
                                    },
                                    as_node=START
                                )
                                res = await compiled_graph.ainvoke(None, config)
                            else:
                                logger.info(f"Resuming active workflow turn from checkpoint for session {state.session_id}")
                                res = await compiled_graph.ainvoke(None, config)
                        else:
                            res = await compiled_graph.ainvoke(state, config)
                        
                        final_state = GraphState(**res)

                        
                        # Clean up messages history: keep only original conversation + the final summary message
                        last_user_idx = -1
                        for idx, msg in enumerate(final_state.messages):
                            if msg.role == "user":
                                last_user_idx = idx
                        
                        summary_content = final_state.accumulated_results.get("last_agent_summary", "No summary report was generated.")
                        summary_msg = Message(
                            role="assistant",
                            content=f"Workflow completed successfully!\n\nSummary:\n{summary_content}"
                        )
                        
                        final_messages = final_state.messages[:last_user_idx + 1] + [summary_msg]
                        final_state.messages = final_messages
                        
                        return final_state
        except Exception as e:
            current_err = e
            while hasattr(current_err, "exceptions") and current_err.exceptions:
                current_err = current_err.exceptions[0]
            raise current_err

