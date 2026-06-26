import os
from dotenv import load_dotenv

# Load the local .env file
load_dotenv()

class Settings:
    
    GEMINI_BASE_URL: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    
    # We can even construct helper properties dynamically!
    @property
    def gemini_url(self) -> str:
        gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        if not gemini_api_key:
            raise ValueError(
                "❌ CRITICAL ERROR: 'GEMINI_API_KEY' is missing or could not be read from your environment/ .env file!"
            )
        return f"{self.GEMINI_BASE_URL}/v1beta/interactions"
    
    @property
    def ollama_url(self) -> str:
        return f"{self.OLLAMA_BASE_URL}/api/chat"

# We instantiate a single, global settings object
settings = Settings()