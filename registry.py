import json, sys, os
from schemas.tool_schemas import DiskQueryInput, DiskQueryOutput, TimeQueryInput, TimeQueryOutput, WebQueryInput, WebQueryOutput
from schemas.tool_schemas import SearchQueryInput, SearchQueryOutput, ListDirectoryInput, ListDirectoryOutput, ChangeDirectoryInput, ChangeDirectoryOutput
from schemas.tool_schemas import GetDirectoryInput, GetDirectoryOutput, ReadFileInput, ReadFileOutput
from services.disk_service import get_disk_usage
from services.time_service import get_time
from services.web_service import fetch_web_content
from services.search_service import search_local_files, list_directory_contents, resolve_and_validate_path, read_local_file
from mcp.server.mcpserver import MCPServer
import asyncio

mcp = MCPServer("SystemMonitor")
current_working_directory = os.path.dirname(os.path.abspath(__file__))

@mcp.tool()
async def get_disk_usage_handler(query: DiskQueryInput):
    """Used to fetch the storage space utilization of the device"""
    disk_details = get_disk_usage()
    
    disk_ = DiskQueryOutput(
        total=f"{disk_details['total']}", 
        free=f"{disk_details['free']}", 
        used=f"{disk_details['used']}"
    )
    
    return getattr(disk_, query.type.lower())

@mcp.tool()
async def get_time_handler(query: TimeQueryInput):
    """Used to fetch the date and time across timezones"""
    sys.stderr.write(f"\n[Executing Tool: get_time] for timezone: '{query.time_zone}'\n")

    date_time_data = get_time(time_zone=query.time_zone)
    
    time_ = TimeQueryOutput(
        date=f"{date_time_data['date']}", 
        time=f"{date_time_data['time']}", 
        timezone=f"{date_time_data['timezone']}", 
        both=f"{date_time_data['both']}"
    )
    
    return getattr(time_, query.type)

@mcp.tool()
async def fetch_web_content_handler(query: WebQueryInput):
    """Used to access the Internet and get raw text details from a webpage."""
    sys.stderr.write(f"\n[Executing Tool: fetch_web_content] for URL: '{query.url}'\n")

    raw_data = await fetch_web_content(query.url)
    raw_data = WebQueryOutput(
        url=raw_data['url'],
        title=raw_data['title'],
        content=raw_data['content']
    )
    
    return raw_data.content

@mcp.tool()
async def search_local_files_handler(query: SearchQueryInput):
    """Used to search the local file system and get matching results"""
    global current_working_directory
    target_directory = query.directory or current_working_directory
    sys.stderr.write(f"\n[Executing Tool: search_local_files] for: '{query.keyword}'\n")
    
    raw_data = await asyncio.to_thread(search_local_files, target_directory, query.keyword)
    validate_data = SearchQueryOutput(
        directory=raw_data['directory'],
        keyword=raw_data['keyword'],
        matches=raw_data['matches'],
        truncated=raw_data['truncated'],
        message=raw_data['message']
    )
    
    return validate_data.matches

@mcp.tool()
async def list_directory_contents_handler(query: ListDirectoryInput):
    """Used to get the directories and files inside a directory"""
    global current_working_directory
    target_directory = query.directory or current_working_directory
    sys.stderr.write(f"\n[Executing Tool: search_local_files] for: '{target_directory}'\n")
    
    raw_data = list_directory_contents(target_directory)
    validate_data = ListDirectoryOutput(
        directory = raw_data.get('directory'),
        directories = raw_data.get('directories'),
        files = raw_data.get('files'),
        error = raw_data.get('error')
    )
    
    return validate_data.model_dump_json(exclude={"error"})

@mcp.tool()
async def resolve_and_validate_path_handler(query: ChangeDirectoryInput):
    global current_working_directory
    sys.stderr.write(f"\n[Executing Tool: change_directory] for: '{query.path}'\n")
    try:
        new_path = resolve_and_validate_path(current_working_directory, query.path)
        current_working_directory = new_path
        raw_data = {
            'current_directory': current_working_directory
        }
    except Exception as e:
        raw_data = {
            'current_directory': current_working_directory,
            'error': str(e)
        }
    validated_output = ChangeDirectoryOutput(**raw_data)
    if validated_output.error:
        return validated_output.error
    else:
        return f"Directory changed. Current location is now: {validated_output.current_directory}"

@mcp.tool()
async def get_current_directory_handler(query: GetDirectoryInput):
    """Get the active current working directory path of this session (pwd)."""
    sys.stderr.write(f"\n[Executing Tool: current_directory to get the current path] '\n")

    global current_working_directory
    
    raw_data = {
        'current_directory': current_working_directory
    }
    validated_output = GetDirectoryOutput(**raw_data)
    
    return validated_output.current_directory

@mcp.tool()
async def read_local_file_handler(query: ReadFileInput):
    """To Read the files"""
    sys.stderr.write(f"\n[Executing Tool: read_local_files to read the file at {query.file_path}] '\n")
    
    global current_working_directory
    current_dir = query.directory or current_working_directory
    
    try:
        raw_data = read_local_file(current_dir, query.file_path)
    except Exception as e:
        raw_data = {"file_path": None, "error": str(e)}
    validated_data = ReadFileOutput(**raw_data)
    if validated_data.error: return validated_data.error
    else: return validated_data.content
        
    
tools_path = os.path.join(current_working_directory, "schemas", "tools.json")

with open(tools_path) as f:
    tools_list = json.load(f)

disk_tool_schema = tools_list[0]
time_tool_schema = tools_list[1]
web_tool_schema = tools_list[2]
local_search_tool_schema = tools_list[3]
list_directory_tool_schema = tools_list[4]
resolve_and_validate_path_schema = tools_list[5]
get_current_directory_schema = tools_list[6]
read_file_tool_schema = tools_list[7]

available_tools = {
    "get_disk_usage": {
        "func": get_disk_usage_handler,
        "input_model": DiskQueryInput,
        "schema": disk_tool_schema
    },
    "get_time": {
        "func": get_time_handler,
        "input_model": TimeQueryInput,
        "schema": time_tool_schema
    },
    "fetch_web_content": {
        "func": fetch_web_content_handler,
        "input_model": WebQueryInput,
        "schema": web_tool_schema
    },
    "search_local_files": {
        "func": search_local_files_handler,
        "input_model": SearchQueryInput,
        "schema": local_search_tool_schema
    },
    "list_directory_contents": {
        "func": list_directory_contents_handler,
        "input_model": ListDirectoryInput,
        "schema": list_directory_tool_schema
    },
    "change_directory": {
        "func": resolve_and_validate_path_handler,
        "input_model": ChangeDirectoryInput,
        "schema": resolve_and_validate_path_schema
    },
    "get_current_directory": {
        "func": get_current_directory_handler,
        "input_model": GetDirectoryInput,
        "schema": get_current_directory_schema
    },
    "read_local_file": {
    "func": read_local_file_handler,
    "input_model": ReadFileInput,
    "schema": read_file_tool_schema
    }
}

if __name__ == "__main__":
    mcp.run(transport="stdio")