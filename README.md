# Sync your scheduled telegram messages to your macOS Calendar

This script retrieves all your scheduled Telegram messages (from your own chat) and creates or updates events in your macOS Calendar based on those messages.

## How to Run

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
3. Get `API_ID`, `API_HASH` from [https://core.telegram.org/api/obtaining_api_id](https://core.telegram.org/api/obtaining_api_id) and set them to `config.json` file.
4. Run `sync_calendar.py` manually, or configure cron for it.
