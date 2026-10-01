import os
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient
load_dotenv()
api_id=int(os.environ["TG_API_ID"]); api_hash=os.environ["TG_API_HASH"]
session=os.getenv("TG_SESSION","demob_user"); Path("data").mkdir(exist_ok=True)
client=TelegramClient(f"data/{session}",api_id,api_hash)
async def main():
    await client.start()
    me=await client.get_me()
    print(f"Авторизация успешна: id={me.id}, username=@{me.username or '-'}")
    print(f"Session: data/{session}.session")
with client: client.loop.run_until_complete(main())
