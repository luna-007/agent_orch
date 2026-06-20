import json, sys, os
from schemas.tool_schemas import DiskQueryInput, DiskQueryOutput, TimeQueryInput, TimeQueryOutput, WebQueryInput, WebQueryOutput
from schemas.tool_schemas import SearchQueryInput, SearchQueryOutput, ListDirectoryInput, ListDirectoryOutput, ChangeDirectoryInput, ChangeDirectoryOutput
from schemas.tool_schemas import GetDirectoryInput, GetDirectoryOutput
from services.disk_service import get_disk_usage
from services.time_service import get_time
from services.web_service import fetch_web_content
from services.search_service import search_local_files, list_directory_contents, resolve_and_validate_path
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("SystemMonitor")
current_working_directory = os.path.dirname(os.path.abspath(__file__))


@mcp.tool()
def get_disk_usage_handler(query: DiskQueryInput):
    """Used to fetch the storage space utilization of the device"""
    disk_details = get_disk_usage()
    
    disk_ = DiskQueryOutput(
        total=f"{disk_details['total']}", 
        free=f"{disk_details['free']}", 
        used=f"{disk_details['used']}"
    )
    
    return getattr(disk_, query.type.lower())

@mcp.tool()
def get_time_handler(query: TimeQueryInput):
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
def fetch_web_content_handler(query: WebQueryInput):
    """Used to access the Internet and get raw text details from a webpage."""
    sys.stderr.write(f"\n[Executing Tool: fetch_web_content] for URL: '{query.url}'\n")

    raw_data = fetch_web_content(query.url)
    raw_data = WebQueryOutput(
        url=raw_data['url'],
        title=raw_data['title'],
        content=raw_data['content']
    )
    
    return raw_data.content

@mcp.tool()
def search_local_files_handler(query: SearchQueryInput):
    """Used to search the local file system and get matching results"""
    global current_working_directory
    target_directory = query.directory or current_working_directory
    sys.stderr.write(f"\n[Executing Tool: search_local_files] for: '{query.keyword}'\n")
    
    raw_data = search_local_files(target_directory, query.keyword)
    validate_data = SearchQueryOutput(
        directory= raw_data['directory'],
        keyword= raw_data['keyword'],
        matches=raw_data['matches']
    )
    
    return validate_data.matches

@mcp.tool()
def list_directory_contents_handler(query: ListDirectoryInput):
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
    
    return validate_data.files

@mcp.tool()
def resolve_and_validate_path_handler(query: ChangeDirectoryInput):
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
def get_current_directory_handler(query: GetDirectoryInput):
    """Get the active current working directory path of this session (pwd)."""
    sys.stderr.write(f"\n[Executing Tool: current_directory to get the current path] '\n")

    global current_working_directory
    
    raw_data = {
        'current_directory': current_working_directory
    }
    validated_output = GetDirectoryOutput(**raw_data)
    
    return validated_output.current_directory
        
    
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
    }
}

if __name__ == "__main__":
    mcp.run(transport="stdio")