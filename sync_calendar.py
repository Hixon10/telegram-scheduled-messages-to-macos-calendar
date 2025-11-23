import asyncio
from telethon import TelegramClient
from telethon.tl.functions.messages import GetScheduledHistoryRequest
import json
import subprocess
import datetime
import re
from typing import List, Dict
from dataclasses import dataclass
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
LOG_PATH = BASE_DIR / "sync_log.log"

### Logging configuration (5MB size, keep 2 backups)
handler = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=2)

formatter = logging.Formatter(
    fmt="[%(asctime)s] - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(handler)

logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

### App configuration
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

API_ID = config["API_ID"]
API_HASH = config["API_HASH"]
SESSION_NAME = config["SESSION_NAME"]
CALENDAR_NAME = config["CALENDAR_NAME"]


### Script code
def _run_jxa(js_code):
    process = subprocess.Popen(
        ["osascript", "-l", "JavaScript", "-e", js_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise Exception(f"AppleScript/JXA Error: {stderr.strip()}")
    return stdout.strip()


def _format_dt_for_js(dt: datetime):
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.isoformat()
    return dt


@dataclass
class CalendarEvent:
    id: int
    title: str
    startDate: datetime


def add_calendar_event(event: CalendarEvent, calendar_name: str) -> None:
    iso_date = _format_dt_for_js(event.startDate)
    js_code = f"""
    var app = Application("Calendar");
    var calName = {json.dumps(calendar_name)};
    var calendars = app.calendars.whose({{name: calName}});
    if (calendars.length === 0) throw new Error("Calendar '" + calName + "' not found.");
    
    var cal = calendars[0];
    var startDate = new Date("{iso_date}");
    var endDate = new Date(startDate.getTime() + (60 * 60 * 1000)); // 1 hour duration
    var customIdTag = "[ID:" + {json.dumps(event.id)} + "]";
    
    var event = app.Event({{
        summary: {json.dumps(event.title)},
        startDate: startDate,
        endDate: endDate,
        description: customIdTag
    }});
    cal.events.push(event);
    "Success";
    """
    _run_jxa(js_code)
    logging.info(
        f"Event '{event.title}' with id '{event.id}' added to '{calendar_name}'."
    )


def update_calendar_event(event: CalendarEvent, calendar_name: str) -> None:
    """
    Updates title and time.
    Includes logic to prevent "Start date must be before end date" errors
    by determining the safe order of updates.
    """
    iso_date = _format_dt_for_js(event.startDate)

    js_code = f"""
    var app = Application("Calendar");
    var calName = {json.dumps(calendar_name)};
    var calendars = app.calendars.whose({{name: calName}});
    if (calendars.length === 0) throw new Error("Calendar '" + calName + "' not found.");
    
    var cal = calendars[0];
    var targetId = "[ID:" + {json.dumps(event.id)} + "]";
    var events = cal.events.whose({{description: {{_contains: targetId}}}});
    var foundEvents = events();
    
    if (foundEvents.length === 0) {{
        throw new Error("Event with ID " + {json.dumps(event.id)} + " not found.");
    }}
    
    var evt = foundEvents[0];
    
    // Calculate new times
    var newStartDate = new Date("{iso_date}");
    var newEndDate = new Date(newStartDate.getTime() + (60 * 60 * 1000)); // Reset to 1 hour
    
    var currentStartDate = evt.startDate();
    
    evt.summary = {json.dumps(event.title)};
    
    // SAFETY CHECK: Order of operations matters to prevent invalid states
    if (newStartDate.getTime() > currentStartDate.getTime()) {{
        // Moving forward: Update END first to make room
        evt.endDate = newEndDate;
        evt.startDate = newStartDate;
    }} else {{
        // Moving backward: Update START first to make room
        evt.startDate = newStartDate;
        evt.endDate = newEndDate;
    }}
    
    // Ensure description isn't wiped out if user manually edited it (optional, here we force reset ID)
    evt.description = targetId;
    
    "Updated";
    """
    try:
        _run_jxa(js_code)
        logging.info(f"Event '{event.title}' with id '{event.id}' updated.")
    except Exception as e:
        logging.error(f"Failed to update: {e}")


def get_all_calendar_events(calendar_name: str) -> dict[int, CalendarEvent]:
    js_code = f"""
    var app = Application("Calendar");
    var calName = {json.dumps(calendar_name)};
    var calendars = app.calendars.whose({{name: calName}});
    if (calendars.length === 0) throw new Error("Calendar '" + calName + "' not found.");
    
    var cal = calendars[0];
    var events = cal.events();
    var output = [];
    
    for (var i = 0; i < events.length; i++) {{
        var evt = events[i];
        var desc = evt.description();
        var start = evt.startDate();
        var summary = evt.summary();
        if (desc && desc.includes("[ID:")) {{
            output.push({{ description: desc, isoDate: start.toISOString(), title: summary }});
        }}
    }}
    JSON.stringify(output);
    """
    try:
        result_json = _run_jxa(js_code)
        raw_events = json.loads(result_json)
        parsed_events: Dict[int, CalendarEvent] = {}
        for item in raw_events:
            match = re.search(r"\[ID:(.*?)\]", item.get("description", ""))
            if match:
                dt = datetime.datetime.fromisoformat(
                    item.get("isoDate").replace("Z", "+00:00")
                )
                id = int(match.group(1))

                event = CalendarEvent(id=id, title=item.get("title", ""), startDate=dt)
                parsed_events[id] = event
        return parsed_events
    except Exception as e:
        logging.error(
            f"Error fetching events from macOS calendar '{calendar_name}': {e}"
        )
        return []


def sync_events(telegram_events: List[CalendarEvent], calendar_name: str) -> None:
    logging.info(
        f"Sync is starting: got {len(telegram_events)} events from telegram to sync."
    )

    existing_events = get_all_calendar_events(calendar_name)
    logging.info(
        f"Calendar '{calendar_name}' contains {len(existing_events)} events before sync."
    )

    added = 0
    updated = 0

    for telegram_event in telegram_events:
        existing = existing_events.get(telegram_event.id)

        # Case 1 — Event does not exist in calendar -> ADD
        if existing is None:
            add_calendar_event(telegram_event, calendar_name)
            added += 1
            continue

        # Case 2 — Exists but changed -> UPDATE
        if (
            telegram_event.title != existing.title
            or telegram_event.startDate != existing.startDate
        ):
            update_calendar_event(telegram_event, calendar_name)
            updated += 1
            continue

        logging.debug(
            f"Event '{telegram_event.title}' with id '{telegram_event.id}' not changed."
        )

    if added == 0 and updated == 0:
        logging.info("Sync has finished. No new events updated or added.")
    else:
        logging.info(
            f"Sync has finished. Added {added} events, updated {updated} events."
        )


async def main():
    logging.info("Script started")
    # We use 'async with' to automatically start and stop the client
    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        # Ensure you are logged in
        if not await client.is_user_authorized():
            logging.warning(
                "Script is not authorized. Please run it manually once to log in."
            )
            logging.warning("You will be asked for your phone number and a login code.")
            await client.send_code_request(await client.get_input_entity("me"))
            await client.sign_in(
                await client.get_input_entity("me"), input("Enter code: ")
            )
            logging.info("Logged in successfully. Please run the script again.")
            return

        # Get the 'Saved Messages' chat (referred to as 'me' or 'self')
        saved_messages_peer = await client.get_input_entity("me")

        logging.info("Started getting messages from telegram.")

        # Call the API method to get scheduled messages
        result = await client(
            GetScheduledHistoryRequest(
                peer=saved_messages_peer,
                hash=0,  # Not used for the first request
            )
        )

        # Print the messages
        if not result.messages:
            logging.info("No scheduled messages found in telegram. Nothing to sync.")
            return

        logging.info(f"Got {len(result.messages)} scheduled message(s) from telegram.")

        telegram_events: List[CalendarEvent] = []

        for msg in reversed(result.messages):
            # 'msg.date' is the UTC datetime when it's scheduled to be sent
            # print(f"Scheduled for: {msg.date.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            # print(f"Message: {msg.message}\n")
            # print(f"Message id: {msg.id}\n")
            event = CalendarEvent(
                id=msg.id,
                title=msg.message,  # fallback to empty string if message is None
                startDate=msg.date.replace(
                    tzinfo=datetime.timezone.utc
                ),  # ensure UTC tzinfo
            )
            telegram_events.append(event)

        sync_events(telegram_events, CALENDAR_NAME)


if __name__ == "__main__":
    # This runs the 'main' function
    asyncio.run(main())
