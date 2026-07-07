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

    @staticmethod
    def _flatten_tool_schema(schema: dict) -> dict:
        """Flatten MCP tool schemas by resolving references and unwrapping 'query' wrappers.
        
        The MCP SDK generates nested schemas with references because handler functions
        take a single Pydantic model parameter (e.g., query: DiskQueryInput).
        Small LLMs cannot parse references — they need flat property definitions.
        """
        defs = {}
        if "$defs" in schema and isinstance(schema["$defs"], dict):
            defs.update(schema["$defs"])
        if "definitions" in schema and isinstance(schema["definitions"], dict):
            defs.update(schema["definitions"])
            
        properties = dict(schema.get("properties", {}))
        required = list(schema.get("required", []))
        
        # If there's a single 'query' property, unwrap it
        if len(properties) == 1 and "query" in properties:
            query_prop = properties["query"]
            if isinstance(query_prop, dict):
                if "properties" in query_prop:
                    properties = dict(query_prop.get("properties", {}))
                    required = list(query_prop.get("required", []))
                elif "$ref" in query_prop:
                    ref = query_prop.get("$ref", "")
                    ref_name = ref.split("/")[-1]
                    if ref_name in defs:
                        inner = defs[ref_name]
                        properties = dict(inner.get("properties", {}))
                        required = list(inner.get("required", []))
        
        # Resolve any remaining reference in individual properties
        resolved_props = {}
        for prop_name, prop_def in properties.items():
            if prop_name == "current_dir":
                continue
            if not isinstance(prop_def, dict):
                resolved_props[prop_name] = prop_def
                continue
                
            if "$ref" in prop_def:
                ref = prop_def["$ref"]
                ref_name = ref.split("/")[-1]
                if ref_name in defs:
                    prop_def = dict(defs[ref_name])
            
            # Simplify anyOf unions (e.g., anyOf: [{type: string}, {type: null}]) to just the non-null type
            if "anyOf" in prop_def and isinstance(prop_def["anyOf"], list):
                non_null = [t for t in prop_def["anyOf"] if isinstance(t, dict) and t.get("type") != "null"]
                if non_null:
                    simplified = dict(non_null[0])
                    # Preserve description and default from outer property
                    if "description" in prop_def:
                        simplified["description"] = prop_def["description"]
                    if "default" in prop_def:
                        simplified["default"] = prop_def["default"]
                    prop_def = simplified
                    
            # Strip Pydantic metadata that LLMs don't need
            prop_def = {k: v for k, v in prop_def.items() if k not in ("title",)}
            resolved_props[prop_name] = prop_def
        
        if "current_dir" in required:
            required.remove("current_dir")
            
        return {
            "type": "object",
            "properties": resolved_props,
            "required": required
        }

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
        initial_msg_count = len(state.messages)
        
        while True:
            iter += 1
            if iter >= max_iter:
                logger.warning("Max iterations reached in agent turn.")
                fallback_msg = Message(
                    role="assistant",
                    content=json.dumps({
                        "status": "error",
                        "summary": "I hit the maximum iteration limit while processing the request. This can happen if tools are returning rate-limit errors or empty results. Please try again or refine your query.",
                        "state": "FINISH",
                        "reason": "Iteration limit reached",
                        "tools_called": tools_called
                    })
                )
                on_save(fallback_msg)
                state.messages.append(fallback_msg)
                return state
            
            max_retries = 3
            backoff_factor = 2.0
            response = None
            
            # Clean and filter conversation history to avoid JSON and intermediate message contamination
            messages_list = list(state.messages)
            last_user_idx = -1
            for idx, msg in enumerate(messages_list):
                if msg.role == "user":
                    last_user_idx = idx
            
            cleaned_history = []
            if last_user_idx != -1:
                # 1. Process completed turns (all messages before the last user message)
                prev_messages = messages_list[:last_user_idx]
                
                # Group previous messages by turn. Each user message starts a turn.
                turn_indices = [i for i, m in enumerate(prev_messages) if m.role == "user"]
                
                for t_idx, start_idx in enumerate(turn_indices):
                    end_idx = turn_indices[t_idx + 1] if t_idx + 1 < len(turn_indices) else len(prev_messages)
                    turn_msgs = prev_messages[start_idx:end_idx]
                    
                    # Keep the user query that started this completed turn
                    cleaned_history.append(turn_msgs[0])
                    
                    # Collect all tools called in this turn
                    tools_called_in_turn = []
                    for m in turn_msgs:
                        if m.role == "assistant" and m.tool_calls:
                            for tc in m.tool_calls:
                                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                                if name:
                                    tools_called_in_turn.append(name)
                    
                    # Find the last conversational response from the assistant in this turn
                    last_assistant_msg = None
                    for m in reversed(turn_msgs):
                        if m.role == "assistant" and m.content:
                            if m.tool_calls:
                                continue
                            last_assistant_msg = m
                            break
                    
                    if last_assistant_msg:
                        # If the assistant message content is JSON, parse and extract the human-readable summary
                        content_str = last_assistant_msg.content.strip()
                        if content_str.startswith("{") and content_str.endswith("}"):
                            try:
                                parsed = json.loads(content_str)
                                summary = parsed.get("summary", content_str)
                                reasoning = parsed.get("reason", "")
                                
                                info = f"Summary of response: {summary}"
                                if reasoning:
                                    info += f"\nReasoning/Context: {reasoning}"
                                if tools_called_in_turn:
                                    info += f"\nTools executed in this turn: {', '.join(tools_called_in_turn)}"
                                cleaned_history.append(Message(role="assistant", content=info))
                            except Exception:
                                info = last_assistant_msg.content
                                if tools_called_in_turn:
                                    info += f"\n[Tools executed in this turn: {', '.join(tools_called_in_turn)}]"
                                cleaned_history.append(Message(role="assistant", content=info))
                        else:
                            info = last_assistant_msg.content
                            if tools_called_in_turn:
                                info += f"\n[Tools executed in this turn: {', '.join(tools_called_in_turn)}]"
                            cleaned_history.append(Message(role="assistant", content=info))
                
                # 2. Add current turn messages (from the last user message onwards)
                cleaned_history.append(messages_list[last_user_idx])
                for idx in range(last_user_idx + 1, len(messages_list)):
                    if idx >= initial_msg_count:
                        cleaned_history.append(messages_list[idx])
            else:
                cleaned_history = messages_list

            chat_messages = []
            if system_prompt:
                chat_messages.append(Message(role="system", content=system_prompt))
            for msg in cleaned_history:
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
                                    "parameters": self._flatten_tool_schema(remote_tool.input_schema)
                                }
                            })
                except Exception as e:
                    logger.error(f"Failed to list remote tools from MCP session: {e}")
            
            logger.info(f"Tools resolved: {len(tools_schema)} tools for agent (allowed: {allowed_tool_names}). Names: {[t['function']['name'] for t in tools_schema]}")

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
                        
                        # Inspect the raw MCP schema to determine if the server expects a 'query' wrapper
                        raw_props = target_tool.input_schema.get("properties", {})
                        needs_query_wrap = (
                            len(raw_props) == 1 
                            and "query" in raw_props
                        )
                        
                        # Inject directory context into the flat args
                        # (check inner schema properties via definitions resolution)
                        defs = {}
                        if "$defs" in target_tool.input_schema and isinstance(target_tool.input_schema["$defs"], dict):
                            defs.update(target_tool.input_schema["$defs"])
                        if "definitions" in target_tool.input_schema and isinstance(target_tool.input_schema["definitions"], dict):
                            defs.update(target_tool.input_schema["definitions"])
                            
                        inner_props = raw_props
                        if needs_query_wrap:
                            query_val = raw_props["query"]
                            if isinstance(query_val, dict):
                                if "$ref" in query_val:
                                    ref_name = query_val["$ref"].split("/")[-1]
                                    inner_props = defs.get(ref_name, {}).get("properties", {})
                                else:
                                    inner_props = query_val.get("properties", {})

                        
                        if "current_dir" in inner_props:
                            args["current_dir"] = state.current_working_dir
                        elif "directory" in inner_props and args.get("directory") is None:
                            args["directory"] = state.current_working_dir
                        
                        # Re-wrap flat args into 'query' envelope if server expects it
                        call_args = {"query": args} if needs_query_wrap else args
                            
                        tool_result = await mcp_session.call_tool(tool_call.name, arguments=call_args)
                        
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

                target_calls = [
                    tc for tc in response.tool_calls 
                    if tc.name in known_tool_names and (allowed_tool_names is None or tc.name in allowed_tool_names)
                ]

                # Run purely network/web tools concurrently, but local/stateful tools sequentially
                is_pure_network = len(target_calls) > 0 and all(
                    tc.name in {"web_search", "fetch_web_content"} for tc in target_calls
                )

                if is_pure_network:
                    results = await asyncio.gather(*[execute_tool(tc) for tc in target_calls])
                else:
                    results = []
                    for tc in target_calls:
                        results.append(await execute_tool(tc))
                
                for function_name, tool_output in results:
                    tool_msg = Message(
                        role="tool",
                        tool_name=function_name,
                        content=tool_output
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
