import asyncio
from telethon import TelegramClient
import json

CONFIG_PATH = "/Users/denis/sync-tg-calendar/config.json"
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

API_ID = config["API_ID"]
API_HASH = config["API_HASH"]
SESSION_NAME = config["SESSION_NAME"]    

def compute_ids_hash(ids: set[int]) -> int:
    if not ids:
        return 0  # empty set → hash = 0
    return hash(frozenset(ids)) & 0xFFFFFFFF  # stable 32-bit integer hash

async def main():
    # We use 'async with' to automatically start and stop the client
    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        
        # Ensure you are logged in
        if not await client.is_user_authorized():
            print("Script is not authorized. Please run it manually once to log in.")
            print("You will be asked for your phone number and a login code.")
            await client.send_code_request(await client.get_input_entity('me'))
            await client.sign_in(await client.get_input_entity('me'), input('Enter code: '))
            print("Logged in successfully. Please run the script again.")
            return

        async for msg in client.iter_messages('me', limit=1000, scheduled=True):
            found_messages = True
            print(f"Scheduled for: {msg.date.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f"Message: {msg.message}\n")
            print(f"Message id: {msg.id}\n")

        if not found_messages:
            print("No scheduled messages found.")

if __name__ == "__main__":
    # This runs the 'main' function
    asyncio.run(main())