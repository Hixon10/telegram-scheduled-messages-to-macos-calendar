# Sync Your Scheduled Telegram Messages to Your macOS Calendar

This script retrieves all scheduled Telegram messages (from your personal chat) and creates or updates matching events in the macOS Calendar application.

## How to Run

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
3. Obtain your `API_ID`, `API_HASH` from [https://core.telegram.org/api/obtaining_api_id](https://core.telegram.org/api/obtaining_api_id) and set them to `config.json` file (create this config file from `sample-config.json`).
4. Run `sync_calendar.py` manually, or configure it to run automatically using `launchd` or `cron`.

## How to run sync periodically with launchd

1. Update all paths (python, sync_calendar.py, launchd_error.log, launchd_out.log) in the `com.denis.calendar-sync.plist` file (located in the project root).
2. Copy the updated file to your user LaunchAgents directory:
   ```bash
   cp ./com.denis.calendar-sync.plist ~/Library/LaunchAgents/com.denis.calendar-sync.plist
3. Start the scheduled process:
    ```bash
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.denis.calendar-sync.plist
4. macOS will ask for permission to allow `python` to access the Calendar application. You must grant this permission.    
5. To stop the periodic process, use:
    ```bash
    launchctl bootout ~/Library/LaunchAgents/com.denis.calendar-sync.plist
6. To see the current status of a periodic process, use the following command (If the status is `0`, the script is running. A negative number indicates an error, and you need to check `launchd_error.log` or `sync_log.log` files for details):
   ```bash
   launchctl list | grep com.denis.calendar-sync    
