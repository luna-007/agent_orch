import os
import requests

headers = {
    'x-goog-api-key': os.getenv('GEMINI_API_KEY', ''),
    'Content-Type': 'application/json',
}

json_data = {
    'model': 'gemini-2.5-flash',
    'input': 'Explain how AI works in a few words',
}

response = requests.post('https://generativelanguage.googleapis.com/v1beta/interactions', headers=headers, json=json_data)

print(response.text)