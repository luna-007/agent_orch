import asyncio
import os
import sqlite3
import json
from config import settings
from clients.ollama_client import OllamaClient
from app.orchestrator import Orchestrator
from schemas.agent_schemas import Message
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_ollama():
    llm = OllamaClient()
    orchestrator = Orchestrator(llm, None, settings)
    
    # 1. Fetch raw messages from DB
    conn = sqlite3.connect("agent_memory.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, tool_calls, tool_name FROM Message "
        "WHERE session_id='db51ab75-0259-4623-8075-065f7e560d8a' ORDER BY id ASC;"
    )
    rows = cursor.fetchall()
    conn.close()
    
    messages = []
    for r in rows:
        tc = json.loads(r[2]) if r[2] else None
        messages.append(Message(
            role=r[0],
            content=r[1] or "",
            tool_calls=tc,
            tool_name=r[3]
        ))
        
    print(f"Loaded {len(messages)} messages from DB.")
    
    # 2. Get tools from MCP
    project_dir = "/home/lucifer/Documents/learn_mcp/agent_orchestrator"
    parent_dir = os.path.dirname(project_dir)
    server_path = os.path.join(parent_dir, "mcp_server", "server.py")
    
    server_params = StdioServerParameters(
        command="python3",
        args=[server_path],
        env={**os.environ}
    )
    
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as mcp_session:
            await mcp_session.initialize()
            remote_tools_result = await mcp_session.list_tools()
            
            tools_list = []
            for remote_tool in remote_tools_result.tools:
                flat = orchestrator._flatten_tool_schema(remote_tool.input_schema)
                tools_list.append({
                    "type": "function",
                    "function": {
                        "name": remote_tool.name,
                        "description": remote_tool.description,
                        "parameters": flat
                    }
                })
            
            # Now let's simulate how orchestrator cleans history
            # Set up the dummy state
            from schemas.agent_schemas import GraphState
            state = GraphState(
                session_id="db51ab75-0259-4623-8075-065f7e560d8a",
                messages=messages,
                current_goal="Analyze local filesystem and run system checks",
                accumulated_results={}
            )
            
            # We run the orchestrator's history cleaning logic directly
            iter = 0
            # Clean and filter conversation history
            messages_list = list(state.messages)
            last_user_idx = -1
            for idx, msg in enumerate(messages_list):
                if msg.role == "user":
                    last_user_idx = idx
            
            cleaned_history = []
            if last_user_idx != -1:
                # Turn logic
                prev_messages = messages_list[:last_user_idx]
                turn_indices = [i for i, m in enumerate(prev_messages) if m.role == "user"]
                for t_idx, start_idx in enumerate(turn_indices):
                    end_idx = turn_indices[t_idx + 1] if t_idx + 1 < len(turn_indices) else len(prev_messages)
                    turn_msgs = prev_messages[start_idx:end_idx]
                    cleaned_history.append(turn_msgs[0])
                    
                    tools_called_in_turn = []
                    for m in turn_msgs:
                        if m.role == "assistant" and m.tool_calls:
                            for tc in m.tool_calls:
                                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                                if name:
                                    tools_called_in_turn.append(name)
                                    
                    last_assistant_msg = None
                    for m in reversed(turn_msgs):
                        if m.role == "assistant" and m.content:
                            if m.tool_calls:
                                continue
                            last_assistant_msg = m
                            break
                            
                    if last_assistant_msg:
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
                
                cleaned_history.append(messages_list[last_user_idx])
                for idx in range(last_user_idx + 1, len(messages_list)):
                    cleaned_history.append(messages_list[idx])
            else:
                cleaned_history = messages_list
                
            chat_messages = []
            system_prompt = "You are the SysAdmin agent. Your job is to query or inspect local system files and directory configurations. You have access to: get_disk_usage, search_local_files, list_directory_contents, change_directory, get_current_directory, read_local_file, write_local_file, get_system_info. If the user asks to read, search, list, or check files or directories, you MUST use the appropriate tool (e.g. read_local_file, search_local_files, list_directory_contents). Analyze the user query, use your tools to inspect system details, and output your final structured JSON findings."
            chat_messages.append(Message(role="system", content=system_prompt))
            for msg in cleaned_history:
                if msg.role != "system":
                    chat_messages.append(msg)
                    
            print(f"Cleaned history message count: {len(chat_messages)}")
            
            try:
                res = await llm.chat(chat_messages, tools_list)
                print("SUCCESS!")
                print("Content:", res.content)
                print("Tool calls:", res.tool_calls)
            except Exception as e:
                print("FAILED with exception:", repr(e))

if __name__ == "__main__":
    asyncio.run(test_ollama())
