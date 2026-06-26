import json
from schemas.tool_schemas import Message
from registry import available_tools
from config import settings
from services.memory_service import initialize_db, save_message_to_db
from cli import handle_startup_menu
from services.ai_services import generate_session_title
from services.memory_service import update_session_name
from schemas.llm_schema import LLMClient
from typing import Callable

from clients.ollama_client import OllamaClient

llm = OllamaClient()

initialize_db()
session_id, messages = handle_startup_menu()
is_new_session = len(messages) == 0


def on_save_callback(msg: Message):
    save_message_to_db(session_id, msg)
    
flat_tools = [config["schema"] for config in available_tools.values()]

def run_turn(
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
        response = llm.chat(messages, tools)
        
        if response.tool_calls:
            assistant_msg = Message(
                role="assistant",
                content=response.content,
                tool_calls=[t.model_dump() for t in response.tool_calls]
            )
            on_save(assistant_msg)
            messages.append(assistant_msg)
            
            for tool_call in response.tool_calls:
                function_name = tool_call.name
                if function_name in available_tools:
                    tool_config = available_tools[function_name]
                    tool_to_run = tool_config["func"]
                    input_model = tool_config["input_model"]
                    raw_arguments = tool_call.arguments
                            
                    validated_input = input_model(**raw_arguments)
                    tool_output = tool_to_run(validated_input)
                            
                    tool_msg = Message(
                        role = "tool",
                        tool_name = function_name,
                        content = json.dumps(tool_output)
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

while True:
    user_input = input("\nyou: ")
    
    if user_input.lower() in ['quit', 'exit']:
        print("Goodbye !")
        break
    
    user_msg = Message(role="user", content=user_input)
    on_save_callback(user_msg)
    messages.append(user_msg)
    
    final_response = run_turn(
        messages=messages,
        llm=llm,
        tools=flat_tools,
        on_save=on_save_callback
    )
    
    print(f"\nFinal Reponse: {final_response.replace('*', '')}")
    
    if is_new_session:
        session_title = generate_session_title(messages[0].content, final_response)
        update_session_name(session_id, session_title)
        is_new_session = False          