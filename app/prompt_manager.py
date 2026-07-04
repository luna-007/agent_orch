import os
import logging

logger = logging.getLogger("agent_orch.prompt_manager")

class PromptManager:
    def __init__(self, prompts_dir: str = None):
        if prompts_dir is None:
            # Default to 'prompts' folder at workspace root
            workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            prompts_dir = os.path.join(workspace_root, "prompts")
        self.prompts_dir = prompts_dir
        self.cache = {}

    def get_prompt(self, name: str, **kwargs) -> str:
        """
        Loads the template for 'name' (optionally appending .txt),
        caches the raw template, and formats it using key-value arguments.
        """
        if not name.endswith(".txt"):
            filename = f"{name}.txt"
        else:
            filename = name

        file_path = os.path.join(self.prompts_dir, filename)

        if file_path not in self.cache:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Prompt template file not found at: {file_path}")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.cache[file_path] = f.read()
            except Exception as e:
                logger.error(f"Error reading prompt template file: {e}")
                raise

        template = self.cache[file_path]
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing required prompt formatting variable {e} for template {name}")
            raise
        except Exception as e:
            logger.error(f"Error formatting prompt template {name}: {e}")
            raise
