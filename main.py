from config import settings
import json, aioconsole, os
from schemas.tool_schemas import GraphState, Message
from registry import available_tools
from services.memory_service import MemoryService
from cli import handle_startup_menu
from services.ai_services import generate_session_title
from schemas.llm_schema import LLMClient
from typing import Callable
import asyncio
import logging
from clients.ollama_client import OllamaClient

from app.orchestrator import Orchestrator
from app.workflow_builder import WorkflowBuilder
from app.intent_classifier import IntentClassifier

logger = logging.getLogger("agent_orch.main")

async def run_turn(
    state: GraphState,
    llm: LLMClient,
    tools: list[dict],
    on_save: Callable[[Message], None],
    max_iter: int = 10,
    system_prompt: str | None = None) -> GraphState :
    
    orchestrator = Orchestrator(llm, available_tools, None, settings)
    return await orchestrator.run_turn(state, on_save, max_iter, system_prompt)

async def agent_loop(session_id: str, messages: list, memory_svc: MemoryService, builder: WorkflowBuilder, classifier: IntentClassifier):
    state = GraphState(
        session_id=session_id,
        messages=messages,
        current_goal="Analyze local filesystem and run system checks",
        accumulated_results={}
    )
    is_new_session = len(state.messages) == 0
    
    def on_save_callback(msg: Message):
        memory_svc.save_message_to_db(state.session_id, msg)
    
    # We dynamically select and build the supervisor for the active session.
    supervisor = None
    
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
        
        if not supervisor:
            # Classify user query intent to select the correct workflow
            workflow_metadata = builder.get_workflow_metadata_list()
            selected_flow = await classifier.classify(user_input, workflow_metadata)
            print(f"[Supervisor] Routing session to workflow: {selected_flow}")
            supervisor = builder.build_supervisor(selected_flow)
            
        # Update current goal dynamically based on active workflow
        state.current_goal = supervisor.goal
            
        # Drive the multi-agent workflow via the supervisor
        state = await supervisor.run_workflow(
            state=state,
            on_save=on_save_callback,
            strict=False
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
    llm = OllamaClient()
    orchestrator = Orchestrator(llm, available_tools, memory_svc, settings)
    
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    manifests_dir = os.path.join(workspace_dir, "manifests")
    
    # Instantiate Builder & Classifier (loads & validates all manifests at boot time)
    builder = WorkflowBuilder(manifests_dir, available_tools, orchestrator)
    classifier = IntentClassifier(llm)
    
    session_id, messages = handle_startup_menu(memory_svc)
    
    asyncio.run(agent_loop(session_id, messages, memory_svc, builder, classifier))
    
if __name__ == "__main__":
    main()