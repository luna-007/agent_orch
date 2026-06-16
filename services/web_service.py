import requests as r
import re

def fetch_web_content(url: str):
    
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = r.get(url, headers=headers, timeout=5)
    match = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE)
    title = match.group(1).strip() if match else "No Title"
    html = re.sub(r'<(script|style).*?>.*?</\1>', '', response.text, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r'<[^>]*>', '', html)
    clean_text = " ".join(clean_text.split())
    clean_text=clean_text[:5000]
    return {
        "url": url,
        "title": title,
        "content": clean_text
    }

