import requests
from config import settings

def generate_session_title(user_prompt: str, assistant_response: str) -> str:
    target_url = settings.ollama_url
    target_model = settings.OLLAMA_MODEL
    
    title_prompt = (
        "You are a session title generator. Read the following first turn of a conversation "
        "and summarize it into a clean, human-readable title of no more than 4 words. "
        "Return ONLY the title string. Do not include quotes, punctuation, markdown, or conversational filler.\n\n"
        f"User: {user_prompt}\n"
        f"Assistant: {assistant_response}"
    )
    
    payload = {
        "model": target_model,
        "messages": [{"role": "user", "content": title_prompt}],
        "think": False,
        "stream": False
    }
    
    response = requests.post(target_url, json=payload)
    response_data = response.json()
    final_response = response_data.get("message", {}).get("content", "")
    final_response = final_response.replace("*", "")
    return final_response
