# Telegram Demob Live

24/7 RTMP Live Story with a countdown to 15.10.2026 on your personal Telegram profile.

Set TG_API_ID and TG_API_HASH in .env. Run `python auth.py` once to create the Telegram session, then start the Docker container.

Railway requires a persistent Volume mounted at /app/data so the Telegram session survives redeploys.

Never commit .env or data/.
