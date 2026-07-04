import re
import json
import asyncio
import logging
from typing import Callable
from schemas.tool_schemas import GraphState, Message, AgentOutput
from schemas.llm_schema import LLMClient
from registry import ToolRegistry
from services.memory_service import MemoryService
from services.search_service import resolve_and_validate_path
from config import Settings

logger = logging.getLogger("agent_orch.orchestrator")

class Orchestrator:
    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        memory_svc: MemoryService | None,
        config: Settings | None
    ):
        self.llm = llm
        self.registry = registry
        self.memory_svc = memory_svc
        self.config = config

    def parse_agent_output(self, text: str, tools_called: list[str]) -> AgentOutput:
        clean_text = text.strip() if text else ""
        clean_text = re.sub(r"<think>.*?</think>", "", clean_text, flags=re.DOTALL).strip()
        if "</think>" in clean_text:
            clean_text = clean_text.split("</think>")[-1].strip()
        
        # Tier 1: Strict JSON
        try:
            data = json.loads(clean_text)
            if isinstance(data, dict):
                if "tools_called" not in data or not data["tools_called"]:
                    data["tools_called"] = tools_called
                return AgentOutput(**data)
        except Exception:
            pass

        # Tier 2: Markdown JSON code block
        block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", clean_text, re.DOTALL | re.IGNORECASE)
        if block_match:
            try:
                data = json.loads(block_match.group(1).strip())
                if isinstance(data, dict):
                    if "tools_called" not in data or not data["tools_called"]:
                        data["tools_called"] = tools_called
                    return AgentOutput(**data)
            except Exception:
                pass

        # Tier 3: Loose JSON regex match (first { to last })
        loose_match = re.search(r"(\{.*\})", clean_text, re.DOTALL)
        if loose_match:
            try:
                data = json.loads(loose_match.group(1).strip())
                if isinstance(data, dict):
                    if "tools_called" not in data or not data["tools_called"]:
                        data["tools_called"] = tools_called
                    return AgentOutput(**data)
            except Exception:
                pass

        # Fallback to unstructured text
        return AgentOutput(
            status="success",
            summary=clean_text,
            state="FINISH",
            reason="Fallback parsed from unstructured text",
            tools_called=tools_called
        )

    async def run_turn(
        self,
        state: GraphState,
        on_save: Callable[[Message], None],
        max_iter: int = 10,
        system_prompt: str | None = None,
        allowed_tool_names: list[str] | None = None
    ) -> GraphState:
        iter = 0
        tools_called = []
        
        while True:
            iter += 1
            if iter >= max_iter:
                raise RuntimeError("Max Iterations reached")
            
            max_retries = 3
            backoff_factor = 2.0
            
            response = None
            
            # Prepend system prompt to chat messages sent to LLM
            chat_messages = []
            if system_prompt:
                chat_messages.append(Message(role="system", content=system_prompt))
            for msg in state.messages:
                if msg.role != "system":
                    chat_messages.append(msg)

            for attempt in range(max_retries):
                try:
                    response = await self.llm.chat(chat_messages, self.registry.get_schemas(allowed_tool_names))
                    if response:
                        break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise RuntimeError(f"Connection failed due to {e}")
                    else:
                        sleep_time = backoff_factor * (2 ** attempt)
                        logger.warning(f"LLM call failed on attempt {attempt + 1}: {e}. Retrying in {sleep_time}s...")
                        await asyncio.sleep(sleep_time)
                        
            if response is None:
                raise RuntimeError("Failed to retrieve a valid response from the LLM.")
            
            if response.tool_calls:
                async def execute_tool(tool_call):
                    tool_config = self.registry.get(tool_call.name)
                    if not tool_config:
                        return tool_call.name, f"Error: Tool '{tool_call.name}' not found."
                    
                    try:
                        args = dict(tool_call.arguments) if tool_call.arguments else {}
                        if "current_dir" in tool_config["input_model"].model_fields:
                            args["current_dir"] = state.current_working_dir
                        elif "directory" in tool_config["input_model"].model_fields and args.get("directory") is None:
                            args["directory"] = state.current_working_dir
                        
                        validated_input = tool_config["input_model"](**args)
                        result = await tool_config["func"](validated_input)
                        
                        if tool_call.name == "change_directory":
                            try:
                                new_dir = resolve_and_validate_path(state.current_working_dir, tool_call.arguments["path"])
                                state.current_working_dir = new_dir
                            except Exception:
                                pass
                    except Exception as e:
                        logger.error(f"Failed to execute tool '{tool_call.name}': {e}", exc_info=True)
                        result = f"Error executing tool '{tool_call.name}': {str(e)}"
                    return tool_call.name, result
                
                assistant_msg = Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=[t.model_dump() for t in response.tool_calls]
                )
                on_save(assistant_msg)
                state.messages.append(assistant_msg)
                
                # Track tool names executed in this turn
                for tc in response.tool_calls:
                    if self.registry.contains(tc.name) and (allowed_tool_names is None or tc.name in allowed_tool_names):
                        tools_called.append(tc.name)

                results = await asyncio.gather(
                    *[execute_tool(tc) for tc in response.tool_calls if self.registry.contains(tc.name) and (allowed_tool_names is None or tc.name in allowed_tool_names)]
                )
                
                for function_name, tool_output in results:
                    tool_msg = Message(
                        role="tool",
                        tool_name=function_name,
                        content=json.dumps(tool_output)
                    )
                    on_save(tool_msg)
                    state.messages.append(tool_msg)
                
            else:
                # Parse final response to AgentOutput structure
                parsed_output = self.parse_agent_output(response.content, tools_called)
                
                assistant_msg = Message(
                    role="assistant",
                    content=parsed_output.model_dump_json()
                )
                on_save(assistant_msg)
                state.messages.append(assistant_msg)
                return state
