from datetime import datetime
from zoneinfo import ZoneInfo

def get_time(time_zone: str = 'Asia/Kolkata'):
    # Normalize default timezone casing
    if time_zone == 'Asia/kolkata':
        time_zone = 'Asia/Kolkata'

    try:
        time = datetime.now(tz=ZoneInfo(time_zone))
    except Exception:
        try:
            # Try title case (e.g. asia/kolkata -> Asia/Kolkata)
            time = datetime.now(tz=ZoneInfo(time_zone.title()))
        except Exception:
            try:
                # Try upper case (e.g. utc -> UTC)
                time = datetime.now(tz=ZoneInfo(time_zone.upper()))
            except Exception:
                # Fallback to local system timezone if tzdata is missing or zone name is invalid
                time = datetime.now().astimezone()

    data = {
        "date" : f"Today's date is {datetime.date(time)}",
        "time" : f"The current time is {datetime.time(time)}",
        "timezone": f"The Timezone is {time.tzinfo}",
        "both" : f"The current Date and Time is {time}" 
    }
    return data