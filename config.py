import os
from dotenv import load_dotenv

# Load the local .env file
load_dotenv()

class Settings:
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
    
    # We can even construct helper properties dynamically!
    @property
    def api_url(self) -> str:
        return f"{self.OLLAMA_BASE_URL}/api/chat"

# We instantiate a single, global settings object
settings = Settings()