import json
import re
import logging
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from schemas.llm_schema import LLMClient
from schemas.agent_schemas import AgentOutput, Message

logger = logging.getLogger("agent_orch.router")

class RouterDecision(BaseModel):
    current_state: str = Field(description="The named FSM state we are transitioning to")
    reason: str = Field(description="Reasoning behind selecting this state")

class Router:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def decide(
        self,
        ai_context: List[AgentOutput],
        current_goal: str,
        valid_states: List[Dict[str, Any]],
        strict: bool = True,
        messages: List[Message] | None = None
    ) -> RouterDecision:
        # Format history of outputs
        history_str = ""
        for i, out in enumerate(ai_context):
            history_str += f"{i+1}. Agent Output:\n  State: {out.state}\n  Status: {out.status}\n  Summary: {out.summary}\n  Reason: {out.reason}\n\n"
        if not history_str:
            history_str = "No execution history yet. We are starting the workflow.\n"
            # Since no agents have executed yet, restrict valid states to only the starting entry-points.
            # This programmatically prevents the LLM from choosing completed/terminal states.
            valid_names = [s["name"] for s in valid_states]
            starting_names = ["NEW"]
            if "RESEARCH_DONE" in valid_names:
                starting_names.append("RESEARCH_DONE")
            valid_states = [s for s in valid_states if s["name"] in starting_names]

        # Format valid states matrix
        states_str = ""
        for state_item in valid_states:
            states_str += f"- Name: {state_item['name']}\n  Description: {state_item['description']}\n"

        # Format the user's latest query/conversation if available
        conversation_str = ""
        if messages:
            conversation_str = "Current Conversation History:\n"
            # Extract user messages from the end of the history
            for msg in messages[-3:]:
                if msg.role != "system":
                    content_text = msg.content
                    # If it is JSON, parse and extract summary to keep prompt clean
                    if content_text.strip().startswith("{") and content_text.strip().endswith("}"):
                        try:
                            parsed = json.loads(content_text)
                            content_text = parsed.get("summary", content_text)
                        except Exception:
                            pass
                    conversation_str += f"- {msg.role.upper()}: {content_text}\n"
            conversation_str += "\n"

        prompt = f"""You are the Workflow Supervisor Router.
Your job is to analyze the history of actions taken by the agents, the current conversation history, and determine the current FSM state of the workflow.

Overall workflow goal: {current_goal}

Valid FSM States and their descriptions:
{states_str}

{conversation_str}Execution history of prior agents:
{history_str}

Based on the overall workflow goal, the conversation history, and the execution history of prior agents, decide the current FSM state of the workflow.
You MUST output your response STRICTLY as a JSON object in this format:
{{
  "current_state": "<one of the valid FSM state names>",
  "reason": "<reasoning for selecting this state>"
}}
"""
        chat_messages = [Message(role="user", content=prompt)]
        
        # Call the LLM to get FSM decision
        response = await self.llm.chat(chat_messages, None)
        content = response.content.strip() if response and response.content else ""
        
        decision = self._parse_decision(content)
        
        # Validation checks
        valid_names = [s["name"] for s in valid_states]
        if decision.current_state not in valid_names:
            msg = f"Router returned invalid FSM state '{decision.current_state}'. Valid states: {valid_names}"
            if strict:
                raise ValueError(msg)
            else:
                logger.warning(msg)
                decision.current_state = "FINISH"
        
        return decision

    def _parse_decision(self, text: str) -> RouterDecision:
        # Strip thinking blocks if present
        clean_text = text.strip() if text else ""
        clean_text = re.sub(r"<think>.*?</think>", "", clean_text, flags=re.DOTALL).strip()
        if "</think>" in clean_text:
            clean_text = clean_text.split("</think>")[-1].strip()
        
        # Tier 1: Strict JSON
        try:
            data = json.loads(clean_text)
            if isinstance(data, dict):
                return RouterDecision(**data)
        except Exception:
            pass

        # Tier 2: Markdown JSON block
        block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", clean_text, re.DOTALL | re.IGNORECASE)
        if block_match:
            try:
                data = json.loads(block_match.group(1).strip())
                if isinstance(data, dict):
                    return RouterDecision(**data)
            except Exception:
                pass

        # Tier 3: Loose JSON regex match
        loose_match = re.search(r"(\{.*\})", clean_text, re.DOTALL)
        if loose_match:
            try:
                data = json.loads(loose_match.group(1).strip())
                if isinstance(data, dict):
                    return RouterDecision(**data)
            except Exception:
                pass
        
        # If all fail, try to extract any state name from text as a last resort fallback
        logger.warning(f"Could not parse structured JSON from router response: '{clean_text}'")
        raise ValueError(f"Failed to parse RouterDecision from LLM output: {clean_text}")
