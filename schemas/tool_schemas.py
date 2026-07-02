from typing import Literal, Optional, Any
from pydantic import BaseModel, Field

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
    path: str = Field(
        description="This is for storing the target path to move to"
    )
    
class ChangeDirectoryOutput(BaseModel):
    current_directory: str
    error: Optional[str] = None
    
class GetDirectoryInput(BaseModel):
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
    
class GraphState(BaseModel):
    session_id: str
    messages: list[Message]
    current_goal: str
    accumulated_results: dict[str, Any] = Field(default_factory=dict)
    next_step: str | None = None