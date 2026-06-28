import json
from schemas.tool_schemas import Message
from registry import available_tools
from services.memory_service import save_message_to_db
from cli import handle_startup_menu
from services.ai_services import generate_session_title
from services.memory_service import update_session_name
from schemas.llm_schema import LLMClient
from typing import Callable
import asyncio

from clients.ollama_client import OllamaClient

llm = OllamaClient()

flat_tools = [config["schema"] for config in available_tools.values()]

async def run_turn(
    messages: list[Message],
    llm: LLMClient,
    tools: list[dict],
    on_save: Callable[[Message], None],
    max_iter: int = 5) -> str :
    
    iter = 0
    while True:
        iter += 1
        if iter >= max_iter:
            raise RuntimeError("Max Iterations reached")
        response = await llm.chat(messages, tools)
        
        if response.tool_calls:
            assistant_msg = Message(
                role="assistant",
                content=response.content,
                tool_calls=[t.model_dump() for t in response.tool_calls]
            )
            on_save(assistant_msg)
            messages.append(assistant_msg)
            
            async def execute_tools(tool_call):
                tool_config = available_tools[tool_call.name]
                validated_input = tool_config["input_model"](**tool_call.arguments)
                result = await tool_config["func"](validated_input)
                return tool_call.name, result
            
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
                messages.append(tool_msg)
            
        else:
            assistant_msg = Message(
                role="assistant",
                content=response.content
            )
            on_save(assistant_msg)
            messages.append(assistant_msg)
            return response.content

async def agent_loop(session_id: str, messages: list):
    is_new_session = len(messages) == 0
    
    def on_save_callback(msg: Message):
        save_message_to_db(session_id, msg)
    
    
    while True:
        user_input = input("\nyou: ")
        
        if user_input.lower() in ['quit', 'exit']:
            print("Goodbye !")
            break
        
        user_msg = Message(role="user", content=user_input)
        on_save_callback(user_msg)
        messages.append(user_msg)
        
        final_response = await run_turn(
            messages=messages,
            llm=llm,
            tools=flat_tools,
            on_save=on_save_callback
        )
        
        print(f"\nResponse: {final_response.replace('*', '')}")
        
        if is_new_session:
            session_title = generate_session_title(messages[0].content, final_response)
            update_session_name(session_id, session_title)
            is_new_session = False  
            
def main():
    session_id, messages = handle_startup_menu()
    asyncio.run(agent_loop(session_id, messages))
    
if __name__ == "__main__":
    main()