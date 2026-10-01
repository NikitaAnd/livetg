import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

api_id=int(os.environ["TG_API_ID"])
api_hash=os.environ["TG_API_HASH"]

with TelegramClient(StringSession(), api_id, api_hash) as client:
    me=client.get_me()
    print()
    print(f"Авторизация успешна: id={me.id} username=@{me.username or '-'}")
    print()
    print("Скопируй значение ниже в Railway Variable TG_SESSION_STRING:")
    print()
    print(client.session.save())
    print()
    print("Никому не передавай эту строку. Она дает доступ к Telegram-сессии.")
