from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv
import logging, sys
from logging.handlers import RotatingFileHandler
from pydantic_settings import BaseSettings, SettingsConfigDict

console_handler = logging.StreamHandler(sys.stderr)

file_handler = RotatingFileHandler(
    "agent_orch.log",
    maxBytes=1048576,
    backupCount=2,
    encoding="utf-8"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[console_handler, file_handler]
)

# Load the local .env file
load_dotenv()

class Settings(BaseSettings):
    
    
    GEMINI_BASE_URL: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_KEY: str = ""
    
    
    OLLAMA_BASE_URL: str = ""
    OLLAMA_MODEL: str = ""
    
    DATABASE_PATH: str = "agent_memory.db"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    @model_validator(mode="after")
    def validate_required_settings(self) -> "Settings":
        """Verifies that all required local variables are present after env loading."""
        if not self.OLLAMA_BASE_URL:
            raise ValueError("❌ CRITICAL ERROR: 'OLLAMA_BASE_URL' is missing from your .env file!")
        if not self.OLLAMA_MODEL:
            raise ValueError("❌ CRITICAL ERROR: 'OLLAMA_MODEL' is missing from your .env file!")
        return self
    
    # We can even construct helper properties dynamically!
    @property
    def gemini_url(self) -> str:

        if not self.GEMINI_API_KEY:
            raise ValueError(
                "❌ CRITICAL ERROR: 'GEMINI_API_KEY' is missing or could not be read from your environment/ .env file!"
            )
        return f"{self.GEMINI_BASE_URL}/v1beta/interactions"
    
    @property
    def ollama_url(self) -> str:
        return f"{self.OLLAMA_BASE_URL}/api/chat"

# We instantiate a single, global settings object
settings = Settings()