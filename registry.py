import json, sys
from schemas.tool_schemas import DiskQueryInput, DiskQueryOutput, TimeQueryInput, TimeQueryOutput, WebQueryInput, WebQueryOutput
from schemas.tool_schemas import SearchQueryInput, SearchQueryOutput
from services.disk_service import get_disk_usage
from services.time_service import get_time
from services.web_service import fetch_web_content
from services.search_service import search_local_files
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("SystemMonitor")


@mcp.tool()
def get_disk_usage_handler(query: DiskQueryInput):
    disk_details = get_disk_usage()
    
    disk_ = DiskQueryOutput(
        total=f"{disk_details['total']}", 
        free=f"{disk_details['free']}", 
        used=f"{disk_details['used']}"
    )
    
    return getattr(disk_, query.type.lower())

@mcp.tool()
def get_time_handler(query: TimeQueryInput):
    print(f"\n[Executing Tool: get_time] for timezone: '{query.time_zone}'")

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
    sys.stderr.write(f"\n[Executing Tool: search_local_files] for: '{query.keyword}'\n")
    
    raw_data = search_local_files(query.directory, query.keyword)
    validate_data = SearchQueryOutput(
        directory= raw_data['directory'],
        keyword= raw_data['keyword'],
        matches=raw_data['matches']
    )
    
    return validate_data.matches

with open("schemas/tools.json") as f:
    tools_list = json.load(f)

disk_tool_schema = tools_list[0]
time_tool_schema = tools_list[1]
web_tool_schema = tools_list[2]
local_search_tool_schema = tools_list[3]

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
    }
}

if __name__ == "__main__":
    mcp.run(transport="stdio")