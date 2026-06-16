import requests
import json
from schemas.tool_schemas import Message
from registry import available_tools
from config import settings

messages = []

while True:
    user_input = input("\nyou: ")
    messages.append(Message(role='user', content=user_input))
    
    if user_input.lower() in ['quit', 'exit']:
        print("Goodbye !")
        break

    api_url = settings.api_url
    model_name = settings.OLLAMA_MODEL

    payload = {
        "model": model_name,
        "messages": [msg.model_dump() for msg in messages],
        "think": True,
        "stream": False,
        "tools": [tool_config["schema"] for tool_config in available_tools.values()]
    }

    response = requests.post(
        api_url,
        json=payload)

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
                messages.append(Message(**message)) 

                for tool_call in tool_calls:
                    
                    function_name = tool_call.get("function", {}).get("name", {})
        
                    if function_name in available_tools:
                        
                        tool_config = available_tools[function_name]
                        tool_to_run = tool_config["func"]
                        input_model = tool_config["input_model"]
                        raw_arguments = tool_call.get("function", {}).get("arguments", {})
                        
                        validated_input = input_model(**raw_arguments)
                        tool_output = tool_to_run(validated_input)
                        
                        messages.append(Message(
                            role = "tool",
                            tool_name = function_name,
                            content = json.dumps(tool_output)
                        ))
                
                payload["messages"] = [msg.model_dump() for msg in messages]
                
                second_response = requests.post(
                    api_url,
                    json=payload
                )
                
                if second_response.status_code == 200:
                    
                    sec_response_data = second_response.json()
                    final_response = sec_response_data.get("message", {}).get("content", "")
                    
                    print("\n[AI Final Answer]:")
                    print(final_response.replace("*", ""))
                    messages.append(Message(role="assistant", content=final_response))
            else:
                final_response = response_data.get("message", {}).get("content", "")
                print(f"Response: {final_response.replace('*', '')}")
                messages.append(Message(role="assistant", content=final_response))

            
    else: 
        print(f"Error: {response.status_code}")
        print(response.text)
        