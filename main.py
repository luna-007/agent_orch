import requests
import json
from schemas.tool_schemas import Message
from registry import available_tools
from config import settings
from services.memory_service import initialize_db, save_message_to_db
from cli import handle_startup_menu
from services.ai_services import generate_session_title
from services.memory_service import update_session_name

messages = []
initialize_db()
session_id, messages = handle_startup_menu()
is_new_session = len(messages) == 0

def append_and_save(message: Message):
    messages.append(message)
    save_message_to_db(session_id, message)

api_url = settings.api_url
model_name = settings.OLLAMA_MODEL

while True:
    user_input = input("\nyou: ")
    
    if user_input.lower() in ['quit', 'exit']:
        print("Goodbye !")
        break
    
    append_and_save(Message(role='user', content=user_input))
    
    while True:

        payload = {
            "model": model_name,
            "messages": [msg.model_dump() for msg in messages],
            "think": True,
            "stream": False,
            "tools": [tool_config["schema"] for tool_config in available_tools.values()]
        }

        response = requests.post(api_url,json=payload)

        if response.status_code == 200:
            if response.headers.get("Content-Type") == "application/x-ndjson":  # Is streamed
            
                for line in response.iter_lines():
                    if line:
                        chunk = json.loads(line.decode('utf-8'))
                        content = chunk.get('message', {}).get('content', '')
                        content = content.replace("**", '')
                        
                        print(content, end='', flush=True)
                print()
            
            else:
                
                response_data = response.json()
                message = response_data.get("message", {})
                tool_calls = message.get("tool_calls", [])
                
                if tool_calls:
                    append_and_save(Message(**message)) 

                    for tool_call in tool_calls:
                        
                        function_name = tool_call.get("function", {}).get("name", {})
            
                        if function_name in available_tools:
                            
                            tool_config = available_tools[function_name]
                            tool_to_run = tool_config["func"]
                            input_model = tool_config["input_model"]
                            raw_arguments = tool_call.get("function", {}).get("arguments", {})
                            
                            validated_input = input_model(**raw_arguments)
                            tool_output = tool_to_run(validated_input)
                            
                            append_and_save(Message(
                                role = "tool",
                                tool_name = function_name,
                                content = json.dumps(tool_output)
                            ))      
                            
                else:
                    final_response = response_data.get("message", {}).get("content", "")
                    print(f"Response: {final_response.replace('*', '')}")
                    append_and_save(Message(role="assistant", content=final_response))
                    if is_new_session:
                        session_title = generate_session_title(messages[0].content, final_response)
                        update_session_name(session_id, session_title)
                        is_new_session = False
                        break              
                    break                
        else: 
            print(f"Error: {response.status_code}")
            print(response.text)
            break
            