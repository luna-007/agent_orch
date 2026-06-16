import json
from schemas.tool_schemas import DiskQueryInput, DiskQueryOutput, TimeQueryInput, TimeQueryOutput
from services.disk_service import get_disk_usage
from services.time_service import get_time
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("SystemMonitor")


@mcp.tool()
def get_disk_usage_handler(query: DiskQueryInput):
    disk_details = get_disk_usage()
    
    disk_ = DiskQueryOutput(
        total=f"{disk_details['total']}", 
        free=f"{disk_details['free']}", 
        used=f"{disk_details['used']}")
    
    return getattr(disk_, query.type.lower())

@mcp.tool()
def get_time_handler(query: TimeQueryInput):
    print(f"\n[Executing Tool: get_time] for timezone: '{query.time_zone}'")

    date_time_data = get_time(time_zone=query.time_zone)
    
    time_ = TimeQueryOutput(
        date=f"{date_time_data['date']}", 
        time=f"{date_time_data['time']}", 
        timezone=f"{date_time_data['timezone']}", 
        both=f"{date_time_data['both']}")
    
    return getattr(time_, query.type)

# with open("schemas/tools.json") as f:
#     tools_list = json.load(f)

# disk_tool_schema = tools_list[0]
# time_tool_schema = tools_list[1]

# available_tools = {
#     "get_disk_usage": {
#         "func": get_disk_usage_handler,
#         "input_model": DiskQueryInput,
#         "schema": disk_tool_schema
#     },
#     "get_time": {
#         "func": get_time_handler,
#         "input_model": TimeQueryInput,
#         "schema": time_tool_schema
#     }
# }

if __name__ == "__main__":
    mcp.run(transport="stdio")