import json
import sys
import os
import asyncio
import logging
from mcp.server.mcpserver import MCPServer

from schemas.tool_schemas import (
    DiskQueryInput, DiskQueryOutput, TimeQueryInput, TimeQueryOutput, WebQueryInput, WebQueryOutput,
    SearchQueryInput, SearchQueryOutput, ListDirectoryInput, ListDirectoryOutput, ChangeDirectoryInput, ChangeDirectoryOutput,
    GetDirectoryInput, GetDirectoryOutput, ReadFileInput, ReadFileOutput, WebSearchInput, WriteFileInput, SystemInfoInput
)
from services.disk_service import get_disk_usage
from services.time_service import get_time
from services.web_service import fetch_web_content, search_web
from services.search_service import search_local_files, list_directory_contents, resolve_and_validate_path, read_local_file, write_local_file
from services.system_service import get_system_info

logger = logging.getLogger("agent_orch.mcp_server")

mcp = MCPServer("SystemMonitor")
current_working_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@mcp.tool(name="get_disk_usage")
async def get_disk_usage_handler(query: DiskQueryInput):
    """Used to fetch the storage space utilization of the device"""
    disk_details = get_disk_usage()
    disk_ = DiskQueryOutput(
        total=f"{disk_details['total']}", 
        free=f"{disk_details['free']}", 
        used=f"{disk_details['used']}"
    )
    return getattr(disk_, query.type.lower())

@mcp.tool(name="get_time")
async def get_time_handler(query: TimeQueryInput):
    """Used to fetch the date and time across timezones"""
    logger.info(f"Executing Tool: get_time for timezone: '{query.time_zone}'")
    date_time_data = get_time(time_zone=query.time_zone)
    time_ = TimeQueryOutput(
        date=f"{date_time_data['date']}", 
        time=f"{date_time_data['time']}", 
        timezone=f"{date_time_data['timezone']}", 
        both=f"{date_time_data['both']}"
    )
    return getattr(time_, query.type)

@mcp.tool(name="fetch_web_content")
async def fetch_web_content_handler(query: WebQueryInput):
    """Used to access the Internet and get raw text details from a webpage."""
    logger.info(f"Executing Tool: fetch_web_content for URL: '{query.url}'")
    raw_data = await fetch_web_content(query.url)
    raw_data = WebQueryOutput(
        url=raw_data['url'],
        title=raw_data['title'],
        content=raw_data['content']
    )
    return raw_data.content

@mcp.tool(name="search_local_files")
async def search_local_files_handler(query: SearchQueryInput):
    """Used to search the local file system and get matching results"""
    if query.directory is None:
        raise ValueError("Directory path must be provided.")
    logger.info(f"Executing Tool: search_local_files for: '{query.keyword}'")
    raw_data = await asyncio.to_thread(search_local_files, query.directory, query.keyword)
    validate_data = SearchQueryOutput(
        directory=raw_data.get('directory'),
        keyword=raw_data.get('keyword'),
        matches=raw_data.get('matches'),
        truncated=raw_data.get('truncated'),
        message=raw_data.get('message')
    )
    return validate_data.matches

@mcp.tool(name="list_directory_contents")
async def list_directory_contents_handler(query: ListDirectoryInput):
    """Used to get the directories and files inside a directory"""
    if not query.directory:
        raise ValueError("Directory path not provided.")
    logger.info(f"Executing Tool: list_directory_contents for: '{query.directory}'")
    raw_data = list_directory_contents(query.directory)
    validate_data = ListDirectoryOutput(
        directory=raw_data.get('directory'),
        directories=raw_data.get('directories'),
        files=raw_data.get('files'),
        error=raw_data.get('error')
    )
    return validate_data.model_dump_json(exclude={"error"})

@mcp.tool(name="change_directory")
async def resolve_and_validate_path_handler(query: ChangeDirectoryInput):
    """Used to validate and resolve a target directory for change_directory action."""
    logger.info(f"Executing Tool: change_directory for: '{query.path}'")
    try:
        new_path = resolve_and_validate_path(query.current_dir, query.path)
        raw_data = {
            'current_directory': new_path
        }
    except Exception as e:
        raw_data = {
            'current_directory': query.current_dir,
            'error': str(e)
        }
    validated_output = ChangeDirectoryOutput(**raw_data)
    if validated_output.error:
        return validated_output.error
    else:
        return f"Directory changed. Current location is now: {validated_output.current_directory}"

@mcp.tool(name="get_current_directory")
async def get_current_directory_handler(query: GetDirectoryInput):
    """Get the active current working directory path of this session (pwd)."""
    sys.stderr.write(f"\n[Executing Tool: current_directory to get the current path] '\n")
    raw_data = {
        'current_directory': query.current_dir
    }
    validated_output = GetDirectoryOutput(**raw_data)
    return validated_output.current_directory

@mcp.tool(name="read_local_file")
async def read_local_file_handler(query: ReadFileInput):
    """To Read the files"""
    logger.info(f"Executing Tool: read_local_files to read the file at '{query.file_path}'")
    global current_working_directory
    current_dir = query.directory or current_working_directory
    try:
        raw_data = read_local_file(current_dir, query.file_path)
    except Exception as e:
        raw_data = {"file_path": None, "error": str(e)}
    validated_data = ReadFileOutput(**raw_data)
    if validated_data.error:
        return validated_data.error
    else:
        return validated_data.content

@mcp.tool(name="web_search")
async def web_search_handler(query: WebSearchInput):
    """Queries the internet search engine and returns search results."""
    logger.info(f"Executing Tool: web_search for query: '{query.query}'")
    max_results = query.max_results if query.max_results is not None else 10
    return await search_web(query.query, max_results)

@mcp.tool(name="write_local_file")
async def write_local_file_handler(query: WriteFileInput):
    """Writes or creates text content into a local file."""
    logger.info(f"Executing Tool: write_local_file for path: '{query.file_path}'")
    global current_working_directory
    current_dir = query.directory or current_working_directory
    try:
        raw_data = write_local_file(current_dir, query.file_path, query.content)
        return f"File written successfully to {raw_data['file_path']}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

@mcp.tool(name="get_system_info")
async def get_system_info_handler(query: SystemInfoInput):
    """Queries OS details, CPU count, RAM metrics, and system uptime details."""
    logger.info("Executing Tool: get_system_info")
    return get_system_info()

if __name__ == "__main__":
    mcp.run(transport="stdio")
