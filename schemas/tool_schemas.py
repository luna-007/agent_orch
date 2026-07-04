from typing import Literal, Optional, Any
from pydantic import BaseModel, Field
import os

class TimeQueryInput(BaseModel):
    type: Literal["date", "time","timezone","both"] = Field (
        description="This provides the date, time, timezone and the combined date and time data"
    )
    time_zone: str = Field (
        default = "Asia/Kolkata",
        description="This is for updating the timezone like Asia/Kolkata, America/New_York or Europe/London)"
    )
    
class TimeQueryOutput(BaseModel):
    date: str
    time: str
    timezone: str
    both: str
    
class DiskQueryInput(BaseModel):
    type: Literal["Total", "Used", "Free"] = Field(
        description="The specific storage type to retreive."
    )
    
class DiskQueryOutput(BaseModel):
    total: str
    used: str
    free: str
    
class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = Field(
        description = "The role being used"
    )
    content: str
    tool_name:  Optional[str] = None
    tool_calls: Optional[list] = None
    
class WebQueryInput(BaseModel):
    url: str = Field(
        description="This is to be used to browse or access the Internet"
    )
    
class WebQueryOutput(BaseModel):
    url: str
    title: str
    content: str
    
class SearchQueryInput(BaseModel):
    directory: Optional[str] = Field(
        default=None,
        description="The folder path to search, If omitted, defaults to the active current directory"
    )
    keyword: str = Field(
        description="This is the keyword we are searching for"
    )
    
class SearchQueryOutput(BaseModel):
    directory: str | None = None
    keyword: str | None = None
    matches: list[str] | None = None
    truncated: bool | None = None
    message: str | None = None
    
class ListDirectoryInput(BaseModel):
    directory: Optional[str] = Field(
        default=None,
        description="The folder path to search, If omitted, defaults to the active current directory"
    )
    
class ListDirectoryOutput(BaseModel):
    directory: Optional[str] = None
    directories: Optional[list[str]] = None
    files: Optional[list[str]] = None
    error: Optional[str] = None
    
class ChangeDirectoryInput(BaseModel):
    current_dir: str = Field(
        description="The active, current directory of the session."
    )
    path: str = Field(
        description="The folder name, relative path (e.g. '..', 'services'), or absolute path to move to."
    )
    
class ChangeDirectoryOutput(BaseModel):
    current_directory: str
    error: Optional[str] = None
    
class GetDirectoryInput(BaseModel):
    current_dir: str = Field(
        description="The active, current directory of the session."
    )
    pass

class GetDirectoryOutput(BaseModel):
    current_directory: str
    
class ReadFileInput(BaseModel):
    file_path: str 
    directory: Optional[str] = None
    
class ReadFileOutput(BaseModel):
    file_path: Optional[str] = None
    content: Optional[str] = None
    error: Optional[str] = None
    
class WebSearchInput(BaseModel):
    query: str = Field(
        description="The search query string to search on the web."
    )
    max_results: Optional[int] = Field(
        default=5,
        description="The maximum number of search results to return."
    )

class WriteFileInput(BaseModel):
    file_path: str = Field(
        description="The target file path (relative to the active current directory or absolute)."
    )
    content: str = Field(
        description="The text content to write into the file."
    )
    directory: Optional[str] = Field(
        default=None,
        description="The active, current directory of the session."
    )

class SystemInfoInput(BaseModel):
    pass

class GraphState(BaseModel):
    session_id: str
    messages: list[Message]
    current_working_dir: str = Field(
        default_factory=lambda: os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    current_goal: str
    accumulated_results: dict[str, Any] = Field(default_factory=dict)
    next_step: str | None = None

class AgentOutput(BaseModel):
    status: Literal["success", "error", "partial"] = Field(description="The status of the agent run")
    summary: str = Field(description="The summary of actions taken and final answer")
    state: str = Field(description="The target state for the workflow FSM")
    reason: str = Field(default="", description="The reasoning behind selecting the state and final answer")
    tools_called: list[str] = Field(default_factory=list, description="A list of tools used during execution")