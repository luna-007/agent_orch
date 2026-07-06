import json
import re
import logging
from typing import List, Dict
from schemas.llm_schema import LLMClient
from schemas.agent_schemas import Message

logger = logging.getLogger("agent_orch.intent_classifier")

class IntentClassifier:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def classify(self, query: str, workflows: List[Dict]) -> str:
        # Build prompt listing the workflows and their intents/aliases
        workflows_str = ""
        for w in workflows:
            aliases = ", ".join(w.get("aliases", []))
            workflows_str += f"- Name: {w['name']}\n  Intent: {w.get('intent', 'none')}\n  Aliases/Keywords: {aliases}\n"

        prompt = f"""You are the Workflow Intent Classifier.
Analyze the user request and determine which of the available workflows is the best fit.

Available Workflows:
{workflows_str}

User Request: "{query}"

If the request matches the intent or keywords of one of the workflows, select it.
Otherwise, choose "sysadmin_flow" as the default.

You MUST respond STRICTLY in JSON format:
{{
  "workflow": "<name of selected workflow>"
}}
"""
        messages = [Message(role="user", content=prompt)]
        
        try:
            response = await self.llm.chat(messages, None)
            content = response.content.strip() if response and response.content else ""
            
            # 3-tier parsing
            decision = self._parse_json(content)
            selected = decision.get("workflow", "sysadmin_flow")
            
            # Validate it's one of the workflows
            valid_names = [w["name"] for w in workflows]
            if selected in valid_names:
                logger.info(f"Classified query '{query[:40]}...' -> workflow '{selected}'")
                return selected
            
        except Exception as e:
            logger.error(f"Intent classification failed: {e}. Defaulting to sysadmin_flow.")
            
        logger.info(f"Defaulting query '{query[:40]}...' -> workflow 'sysadmin_flow'")
        return "sysadmin_flow"

    def _parse_json(self, text: str) -> dict:
        clean_text = text.strip()
        
        # Tier 1: Strict JSON
        try:
            return json.loads(clean_text)
        except Exception:
            pass

        # Tier 2: Markdown JSON block
        block_match = re.search(r"```\s*(?:json)?\s*(.*?)\s*```", clean_text, re.DOTALL | re.IGNORECASE)
        if block_match:
            try:
                return json.loads(block_match.group(1).strip())
            except Exception:
                pass

        # Tier 3: Loose JSON regex match
        loose_match = re.search(r"(\{.*\})", clean_text, re.DOTALL)
        if loose_match:
            try:
                return json.loads(loose_match.group(1).strip())
            except Exception:
                pass
                
        raise ValueError(f"Could not parse JSON from output: {text}")
