from datetime import datetime
from zoneinfo import ZoneInfo

def get_time(time_zone: str = 'Asia/kolkata'):
    time = datetime.now(tz=ZoneInfo(f"{time_zone.title()}"))
    data = {
        "date" : f"Today's date is {datetime.date(time)}",
        "time" : f"The current time is {datetime.time(time)}",
        "timezone": f"The Timezone is {time.tzinfo}",
        "both" : f"The current Date and Time is {time}" 
    }
    return data
    