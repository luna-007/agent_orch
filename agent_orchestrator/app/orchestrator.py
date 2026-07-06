import re
import json
import asyncio
import logging
import os
from typing import Callable
from mcp import ClientSession
from schemas.agent_schemas import GraphState, Message, AgentOutput
from schemas.llm_schema import LLMClient
from services.memory_service import MemoryService
from config import Settings

logger = logging.getLogger("agent_orch.orchestrator")

class Orchestrator:
    def __init__(
        self,
        llm: LLMClient,
        memory_svc: MemoryService | None,
        config: Settings | None
    ):
        self.llm = llm
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
        allowed_tool_names: list[str] | None = None,
        mcp_session: ClientSession | None = None
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

            # Retrieve remote tools and build schemas
            tools_schema = []
            known_tool_names = set()
            if mcp_session:
                try:
                    remote_tools_result = await mcp_session.list_tools()
                    for remote_tool in remote_tools_result.tools:
                        known_tool_names.add(remote_tool.name)
                        if allowed_tool_names is None or remote_tool.name in allowed_tool_names:
                            tools_schema.append({
                                "type": "function",
                                "function": {
                                    "name": remote_tool.name,
                                    "description": remote_tool.description,
                                    "parameters": remote_tool.inputSchema
                                }
                            })
                except Exception as e:
                    logger.error(f"Failed to list remote tools from MCP session: {e}")

            for attempt in range(max_retries):
                try:
                    response = await self.llm.chat(chat_messages, tools_schema if tools_schema else None)
                    if response:
                        break
                except Exception as e:
                    logger.exception(f"LLM call failed with exception: {repr(e)}")
                    if attempt == max_retries - 1:
                        raise RuntimeError(f"Connection failed due to {repr(e)}")
                    else:
                        sleep_time = backoff_factor * (2 ** attempt)
                        logger.warning(f"LLM call failed on attempt {attempt + 1}: {repr(e)}. Retrying in {sleep_time}s...")
                        await asyncio.sleep(sleep_time)
                        
            if response is None:
                raise RuntimeError("Failed to retrieve a valid response from the LLM.")
            
            if response.tool_calls:
                async def execute_tool(tool_call):
                    if not mcp_session:
                        return tool_call.name, f"Error: No active MCP session available to execute tool '{tool_call.name}'."
                    
                    try:
                        remote_tools_result = await mcp_session.list_tools()
                        target_tool = next((t for t in remote_tools_result.tools if t.name == tool_call.name), None)
                        if not target_tool:
                            return tool_call.name, f"Error: Tool '{tool_call.name}' not found on remote MCP server."
                            
                        args = dict(tool_call.arguments) if tool_call.arguments else {}
                        properties = target_tool.inputSchema.get("properties", {})
                        if "current_dir" in properties:
                            args["current_dir"] = state.current_working_dir
                        elif "directory" in properties and args.get("directory") is None:
                            args["directory"] = state.current_working_dir
                            
                        tool_result = await mcp_session.call_tool(tool_call.name, arguments=args)
                        
                        result_text = ""
                        if hasattr(tool_result, "content") and tool_result.content:
                            result_text = "".join([c.text for c in tool_result.content if hasattr(c, "text")])
                        else:
                            result_text = str(tool_result)
                            
                        # Handle local change_directory side-effect in client state
                        if tool_call.name == "change_directory" or tool_call.name == "resolve_and_validate_path_handler":
                            path_arg = tool_call.arguments.get("path")
                            if path_arg:
                                state.current_working_dir = os.path.abspath(
                                    os.path.join(state.current_working_dir, path_arg)
                                )
                        return tool_call.name, result_text
                    except Exception as e:
                        logger.error(f"Failed to execute remote tool '{tool_call.name}': {e}", exc_info=True)
                        return tool_call.name, f"Error executing remote tool '{tool_call.name}': {str(e)}"
                
                assistant_msg = Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=[t.model_dump() for t in response.tool_calls]
                )
                on_save(assistant_msg)
                state.messages.append(assistant_msg)
                
                # Track tool names executed in this turn
                for tc in response.tool_calls:
                    if tc.name in known_tool_names and (allowed_tool_names is None or tc.name in allowed_tool_names):
                        tools_called.append(tc.name)

                results = await asyncio.gather(
                    *[execute_tool(tc) for tc in response.tool_calls if tc.name in known_tool_names and (allowed_tool_names is None or tc.name in allowed_tool_names)]
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
