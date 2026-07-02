from config import settings
import json, aioconsole
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

logger = logging.getLogger("agent_orch.orchestrator")

flat_tools = [config["schema"] for config in available_tools.values()]

async def run_turn(
    state: GraphState,
    llm: LLMClient,
    tools: list[dict],
    on_save: Callable[[Message], None],
    max_iter: int = 10) -> GraphState :
    
    iter = 0
    while True:
        iter += 1
        if iter >= max_iter:
            raise RuntimeError("Max Iterations reached")
        
        max_retries:int = 3
        backoff_factor:float = 2.0
        
        response = None
        
        for attempt in range(max_retries):
            try:
                response = await llm.chat(state.messages, tools)
                if response:
                    break
            except Exception as e:
                if (attempt == max_retries - 1):
                    raise RuntimeError(f"Connection failed due to {e}")
                else:
                    sleep_time = backoff_factor * (2 ** attempt)
                    logger.warning(f"LLM call failed on attempt {attempt + 1}: {e}. Retrying in {sleep_time}s...")
                    await asyncio.sleep(sleep_time)
                    
        if response is None:
            raise RuntimeError("Failed to retrieve a valid response from the LLM.")
        
        if response.tool_calls:
            async def execute_tools(tool_call):
                tool_config = available_tools[tool_call.name]
                try:
                    validated_input = tool_config["input_model"](**tool_call.arguments)
                    result = await tool_config["func"](validated_input)
                except Exception as e:
                    logger.error(f"Failed to execute tool '{tool_call.name}': {e}", exc_info=True)
                    result = f"Error executing tool '{tool_call.name}': {str(e)}"
                return tool_call.name, result
            
            assistant_msg = Message(
                role="assistant",
                content=response.content,
                tool_calls=[t.model_dump() for t in response.tool_calls]
            )
            on_save(assistant_msg)
            state.messages.append(assistant_msg)
            
            
            results = await asyncio.gather(
                *[execute_tools(tc) for tc in response.tool_calls if tc.name in available_tools]
            )
            
            for function_name, tool_output in results:
                tool_msg = Message(
                    role = "tool",
                    tool_name=function_name,
                    content=json.dumps(tool_output)
                )
                on_save(tool_msg)
                state.messages.append(tool_msg)
            
        else:
            assistant_msg = Message(
                role="assistant",
                content=response.content
            )
            on_save(assistant_msg)
            state.messages.append(assistant_msg)
            return state

async def agent_loop(session_id: str, messages: list, memory_svc: MemoryService, llm: LLMClient):
    
    state = GraphState(
        session_id=session_id,
        messages=messages,
        current_goal="Analyze local filesystem and run system checks",
        accumulated_results={}
    )
    is_new_session = len(state.messages) == 0
    
    def on_save_callback(msg: Message):
        memory_svc.save_message_to_db(state.session_id, msg)
    
    while True:
        try:
            # Non-blocking input wrapper with a 5-minute inactivity timeout!
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
        
        state = await run_turn(
            state=state,
            llm=llm,
            tools=flat_tools,
            on_save=on_save_callback
        )
        final_response = state.messages[-1].content
        
        print(f"\nResponse: {final_response.replace('*', '')}")
        
        if is_new_session:
            session_title = generate_session_title(state.messages[0].content, final_response)
            memory_svc.update_session_name(session_id, session_title)
            is_new_session = False  
            
def main():
    
    memory_svc = MemoryService(settings.DATABASE_PATH)
    llm = OllamaClient()
    
    session_id, messages = handle_startup_menu(memory_svc)
    
    
    asyncio.run(agent_loop(session_id, messages, memory_svc, llm))
    
if __name__ == "__main__":
    main()
    