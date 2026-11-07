"""Converte un orario locale dell'evento in ora italiana, UK e USA (ET/PT)."""
from datetime import datetime
from zoneinfo import ZoneInfo
def convert(date, hhmm, tz):
    d = datetime.strptime(f"{date} {hhmm}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz))
    return {z: d.astimezone(ZoneInfo(z)).strftime("%a %d %b %H:%M") for z in
            ["Europe/Rome","Europe/London","America/New_York","America/Los_Angeles"]}
if __name__ == "__main__": print(convert("2026-11-07","22:00","Europe/London"))
