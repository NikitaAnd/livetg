# Telegram Demob Live

24/7 RTMP Live Story with a countdown to 15.10.2026 on your personal Telegram profile.

## Railway authentication

Railway has no interactive terminal, so do not use `client.start()` there for the first login.

1. Install the dependencies locally.
2. Set `TG_API_ID` and `TG_API_HASH` in a local `.env`.
3. Run `python auth.py` locally.
4. Enter your phone, Telegram login code, and 2FA password if Telegram asks.
5. Copy the generated session string into Railway as `TG_SESSION_STRING`.
6. Railway will start the bot using that already-authorized session without asking for a phone or code.

Telethon documents StringSession as a portable representation of the authorization session. Keep it secret: anyone who gets it can log in as that Telegram account.

The live service uses FFmpeg to generate the countdown video and sends it to Telegram's RTMP live story.

Never commit `.env`, `.session`, or the session string.
