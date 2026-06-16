from typing import Literal, Optional
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
    role: Literal["user", "assistant", "tool"] = Field(
        description = "The role being used"
    )
    content: str
    tool_name:  Optional[str] = None
    tool_calls: Optional[list] = None