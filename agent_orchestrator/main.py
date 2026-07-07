from config import settings
import json, aioconsole, os
from schemas.agent_schemas import GraphState, Message
from services.memory_service import MemoryService
from cli import handle_startup_menu
from services.ai_services import generate_session_title
import asyncio
import logging
from clients.ollama_client import OllamaClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.orchestrator import Orchestrator
from app.workflow_builder import WorkflowBuilder
from app.intent_classifier import IntentClassifier

logger = logging.getLogger("agent_orch.main")

async def agent_loop(session_id: str, messages: list, memory_svc: MemoryService, builder: WorkflowBuilder, classifier: IntentClassifier):
    state = GraphState(
        session_id=session_id,
        messages=messages,
        current_goal="", # Starts empty, gets updated by the workflow
        accumulated_results={}
    )
    
    is_new_session = len(state.messages) == 0
    
    def on_save_callback(msg: Message):
        memory_svc.save_message_to_db(state.session_id, msg)
    
    supervisor = None
    active_flow_name = None
    
    # Build path to decoupled mcp_server/server.py
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(workspace_dir)
    server_path = os.path.join(parent_dir, "mcp_server", "server.py")
    
    server_params = StdioServerParameters(
        command="python3",
        args=[server_path],
        env={
            **os.environ,
            "OLLAMA_BASE_URL": settings.OLLAMA_BASE_URL,
            "OLLAMA_MODEL": settings.OLLAMA_MODEL,
        }
    )
    
    print("[System] Initializing MCP Server subprocess...")
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as mcp_session:
            await mcp_session.initialize()
            print("[System] MCP Server initialized successfully.")
            
            while True:
                try:
                    # Non-blocking input wrapper with a 5-minute inactivity timeout
                    user_input = await asyncio.wait_for(aioconsole.ainput("\nyou: "), timeout=300.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Session {session_id} has expired")
                    print("\n\n[Session Timeout] Closing session due to 5 minutes of inactivity.")
                    break
                
                if user_input.lower() in ['quit', 'exit']:
                    print("Goodbye !")
                    break
                
                user_msg = Message(role="user", content=user_input)
                on_save_callback(user_msg)
                state.messages.append(user_msg)
                
                # Reset the FSM context for the new user query so the agents can run again
                state.accumulated_results["ai_context"] = []
                
                # Classify user query intent to select the correct workflow dynamically on each turn
                workflow_metadata = builder.get_workflow_metadata_list()
                selected_flow = await classifier.classify(user_input, workflow_metadata)
                
                if selected_flow == "none":
                    if active_flow_name != "none":
                        print("[Supervisor] Routing session to Chat Mode (FSM bypassed)")
                        active_flow_name = "none"
                        supervisor = None
                    
                    state.current_goal = "General Conversation"
                    state = await builder.orchestrator.run_turn(
                        state=state,
                        on_save=on_save_callback,
                        system_prompt="You are a helpful, conversational AI assistant with access to local filesystem and system tools. Use tools when needed to answer questions, or respond directly if no tools are necessary.",
                        allowed_tool_names=None,
                        mcp_session=mcp_session
                    )
                else:
                    if selected_flow != active_flow_name or supervisor is None:
                        print(f"[Supervisor] Routing session to workflow: {selected_flow}")
                        supervisor = builder.build_supervisor(selected_flow)
                        active_flow_name = selected_flow
                        
                    # Update current goal dynamically based on active workflow
                    state.current_goal = supervisor.goal
                        
                    # Drive the multi-agent workflow via the supervisor
                    state = await supervisor.run_workflow(
                        state=state,
                        on_save=on_save_callback,
                        strict=False,
                        mcp_session=mcp_session
                    )
                final_response = state.messages[-1].content
                
                try:
                    parsed = json.loads(final_response)
                    display_text = parsed.get("summary", final_response)
                except Exception:
                    display_text = final_response
                    
                print(f"\nResponse: {display_text.replace('*', '')}")
                
                if is_new_session:
                    session_title = generate_session_title(state.messages[0].content, final_response)
                    memory_svc.update_session_name(session_id, session_title)
                    is_new_session = False
            
def main():
    memory_svc = MemoryService(settings.DATABASE_PATH)
    # llm = OllamaClient()
    llm = OllamaClient()
    orchestrator = Orchestrator(llm, memory_svc, settings)
    
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    manifests_dir = os.path.join(workspace_dir, "manifests")
    
    # Instantiate Builder & Classifier (loads & validates all manifests at boot time)
    builder = WorkflowBuilder(manifests_dir, orchestrator)
    classifier = IntentClassifier(llm)
    
    session_id, messages = handle_startup_menu(memory_svc)
    
    asyncio.run(agent_loop(session_id, messages, memory_svc, builder, classifier))
    
if __name__ == "__main__":
    main()
