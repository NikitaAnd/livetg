import asyncio
import math
import os
import random
import signal
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_STRING = os.getenv("TG_SESSION_STRING", "").strip()
SESSION = os.getenv("TG_SESSION", "demob_user")

SERVICE_START = os.getenv("SERVICE_START", "2025-10-15T00:00:00+03:00")
DEMOB_DATE = os.getenv("DEMOB_DATE", "2026-10-15T00:00:00+03:00")
TZ = ZoneInfo(os.getenv("TZ", "Europe/Moscow"))

WIDTH = int(os.getenv("VIDEO_WIDTH", "1280"))
HEIGHT = int(os.getenv("VIDEO_HEIGHT", "720"))
FPS = int(os.getenv("VIDEO_FPS", "30"))
BITRATE = os.getenv("VIDEO_BITRATE", "1800k")
PRESET = os.getenv("VIDEO_PRESET", "veryfast")
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME", "0.16"))

DATA = Path("data")
RUNTIME = Path("runtime")
DATA.mkdir(exist_ok=True)
RUNTIME.mkdir(exist_ok=True)

TIMER_FILE = RUNTIME / "timer.txt"
PROGRESS_FILE = RUNTIME / "progress.txt"
PROGRESS_BAR_FILE = RUNTIME / "progress_bar.txt"
RADIO_LINE_FILE = RUNTIME / "radio_line.txt"

RADIO_LINES = [
    "ПОСЛЕДНИЕ ДНИ. ФИНИШ УЖЕ БЛИЗКО.",
    "ОДИН ЭФИР. ОДИН ФИНИШ. ОДНА ДАТА.",
    "СЧЁТЧИК ИДЁТ. ДОМ СТАНОВИТСЯ БЛИЖЕ.",
    "15 ОКТЯБРЯ 2026 — ТОЧКА НАЗНАЧЕНИЯ.",
    "ФИНИШНАЯ ПРЯМАЯ. ДЕРЖИМ КУРС НА ДОМ.",
    "NIKITA DEMOB RADIO • LIVE 24/7",
]

if SESSION_STRING:
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
else:
    client = TelegramClient(str(DATA / SESSION), API_ID, API_HASH)

ffmpeg_process = None
live_call = None
stop_event = asyncio.Event()


def parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def seconds_left() -> int:
    now = datetime.now(parse_dt(DEMOB_DATE).tzinfo)
    return max(0, int((parse_dt(DEMOB_DATE) - now).total_seconds()))


def format_remaining() -> str:
    remaining = seconds_left()
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, seconds = divmod(remaining, 60)
    return f"{days:02d} ДНЕЙ  •  {hours:02d}:{minutes:02d}:{seconds:02d}"


def progress_percent() -> float:
    start = parse_dt(SERVICE_START)
    end = parse_dt(DEMOB_DATE)
    total = max(1.0, (end - start).total_seconds())
    done = (datetime.now(end.tzinfo) - start).total_seconds()
    return min(100.0, max(0.0, done / total * 100.0))


def make_progress_bar(percent: float, width: int = 54) -> str:
    filled = int(round(width * percent / 100.0))
    return "━" * filled + "─" * (width - filled)


def write_status() -> None:
    percent = progress_percent()
    TIMER_FILE.write_text(format_remaining(), encoding="utf-8")
    PROGRESS_FILE.write_text(f"{percent:.1f}%", encoding="utf-8")
    PROGRESS_BAR_FILE.write_text(make_progress_bar(percent), encoding="utf-8")

    slot = int(datetime.now().timestamp() // 8) % len(RADIO_LINES)
    RADIO_LINE_FILE.write_text(RADIO_LINES[slot], encoding="utf-8")


def find_call(obj):
    if isinstance(obj, types.InputGroupCall):
        return obj
    if isinstance(obj, types.MessageMediaVideoStream):
        return obj.call
    if isinstance(obj, (list, tuple)):
        for item in obj:
            found = find_call(item)
            if found:
                return found
    if hasattr(obj, "__dict__"):
        for item in vars(obj).values():
            found = find_call(item)
            if found:
                return found
    return None


def ffmpeg_cmd(url: str, key: str):
    base = url.rstrip("/")
    if base.startswith("rtmps://") and ":443/" not in base:
        host, path = base[8:].split("/", 1)
        if ":" not in host:
            base = f"rtmps://{host}:443/{path}"

    out = f"{base}/{key}"
    total_seconds = max(
        1,
        int((parse_dt(DEMOB_DATE) - parse_dt(SERVICE_START)).total_seconds()),
    )

    # Premium-looking radio card. All graphics and audio are generated locally
    # by FFmpeg; no external assets are required.
    vf = (
        "drawbox=x=0:y=0:w=iw:h=ih:color=#07090f@1:t=fill,"
        "drawbox=x='70+18*sin(t*0.32)':y=58:w=iw-140:h=604:color=#101827@0.82:t=fill,"
        "drawbox=x=92:y=82:w=iw-184:h=2:color=#b2fa72@0.9:t=fill,"
        "drawbox=x=92:y=636:w=iw-184:h=2:color=#b4a1ff@0.32:t=fill,"
        "drawbox=x='100+900*(0.5+0.5*sin(t*0.65))':y=82:w=120:h=2:color=#ffffff@0.18:t=fill,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "text='NIKITA DEMOB RADIO':fontcolor=#e8edf7:fontsize=24:x=105:y=104,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "text='● LIVE':fontcolor=#ff5f56:fontsize=22:x=w-205:y=104,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "text='ФИНИШНАЯ ПРЯМАЯ':fontcolor=#ffffff:fontsize=55:x=(w-text_w)/2:y=155,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "text='ЭФИР ДО ДЕМБЕЛЯ':fontcolor=#8d9ab0:fontsize=20:x=(w-text_w)/2:y=220,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "textfile=/app/runtime/timer.txt:reload=1:fontcolor=#ffffff:fontsize=66:"
        "x=(w-text_w)/2:y=258,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "text='15 ОКТЯБРЯ 2026  •  ДЕНЬ ФИНИША':fontcolor=#b4a1ff:fontsize=24:"
        "x=(w-text_w)/2:y=350,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "textfile=/app/runtime/progress_bar.txt:reload=1:fontcolor=#b2fa72:fontsize=25:"
        "x=(w-text_w)/2:y=390,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "textfile=/app/runtime/progress.txt:reload=1:fontcolor=#b2fa72:fontsize=23:"
        "x=(w-text_w)/2:y=430,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "textfile=/app/runtime/radio_line.txt:reload=1:fontcolor=#9ca8bb:fontsize=21:"
        "x=(w-text_w)/2:y=535,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "text='ДОМА БУДЕМ. СКОРО.':fontcolor=#ffffff:fontsize=27:"
        "x=(w-text_w)/2:y=575,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "text='DEMOB RADIO  •  LIVE  •  15.10.2026':fontcolor=#5f6c80:fontsize=17:"
        "x=(w-text_w)/2:y=610"
    )

    # A locally generated ambient/electronic bed:
    # root + fifth + octave + high layer, gently modulated and spatialized.
    audio = (
        "[1:a]volume=0.72,tremolo=f=0.09:d=0.55[a1];"
        "[2:a]volume=0.48,tremolo=f=0.07:d=0.45[a2];"
        "[3:a]volume=0.30,tremolo=f=0.11:d=0.35[a3];"
        "[4:a]volume=0.16,tremolo=f=0.13:d=0.30[a4];"
        "[a1][a2][a3][a4]amix=inputs=4:duration=longest,"
        "lowpass=f=2600,"
        "aecho=0.7:0.8:55|110:0.22|0.12,"
        f"volume={MUSIC_VOLUME},"
        "alimiter=limit=0.88,"
        "asplit=2[music][viz];"
        "[viz]showwaves=s=1000x105:mode=cline:rate=30:"
        "colors=#b2fa72,format=rgba[wave]"
    )

    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-re",
        "-f", "lavfi",
        "-i", f"color=c=#07090f:s={WIDTH}x{HEIGHT}:r={FPS}",
        "-f", "lavfi",
        "-i", "sine=frequency=261.63:sample_rate=44100",
        "-f", "lavfi",
        "-i", "sine=frequency=329.63:sample_rate=44100",
        "-f", "lavfi",
        "-i", "sine=frequency=392.00:sample_rate=44100",
        "-f", "lavfi",
        "-i", "sine=frequency=523.25:sample_rate=44100",
        "-filter_complex",
        f"{audio};"
        f"[0:v]{vf}[base];"
        "[base][wave]overlay=x=140:y=455:format=auto:shortest=1[v]",
        "-map", "[v]",
        "-map", "[music]",
        "-c:v", "libx264",
        "-preset", PRESET,
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-g", str(FPS * 2),
        "-b:v", BITRATE,
        "-maxrate", BITRATE,
        "-bufsize", "3M",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        "-f", "flv",
        out,
    ]


async def timer_writer():
    while not stop_event.is_set():
        write_status()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=1)
        except asyncio.TimeoutError:
            pass


async def start_live():
    global live_call

    peer = await client.get_input_entity("me")

    # Check story permissions first. This gives a clean Railway log instead
    # of repeatedly throwing PremiumAccountRequiredError from startLive.
    try:
        await client(functions.stories.CanSendStoryRequest(peer=peer))
    except Exception as exc:
        if "PREMIUM_ACCOUNT_REQUIRED" in str(exc):
            raise RuntimeError(
                "Telegram не разрешает Stories этому аккаунту без Premium. "
                "Live Story/RTMP запуск остановлен."
            ) from exc
        raise

    try:
        result = await client(
            functions.stories.StartLiveRequest(
                peer=peer,
                rtmp_stream=True,
                pinned=False,
                noforwards=False,
                privacy_rules=[types.InputPrivacyValueAllowAll()],
                random_id=random.randint(1, 2**63 - 1),
                messages_enabled=True,
            )
        )
        live_call = find_call(result)
    except Exception as exc:
        if "STORY_LIVE_ALREADY_" not in str(exc):
            raise

    if live_call is None:
        stories = await client(functions.stories.GetPeerStoriesRequest(peer=peer))
        peer_stories = getattr(stories, "stories", stories)
        items = getattr(peer_stories, "stories", peer_stories)

        for item in items:
            media = getattr(item, "media", None)
            if isinstance(media, types.MessageMediaVideoStream):
                live_call = media.call
                break

    if live_call is None:
        raise RuntimeError("InputGroupCall не найден после stories.startLive")

    creds = await client(
        functions.phone.GetGroupCallStreamRtmpUrlRequest(
            peer=peer,
            revoke=False,
            live_story=True,
        )
    )
    return creds.url, creds.key


async def stream(url: str, key: str):
    global ffmpeg_process

    while not stop_event.is_set():
        write_status()
        print("Starting DEMOB RADIO FFmpeg stream", flush=True)

        ffmpeg_process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd(url, key)
        )
        code = await ffmpeg_process.wait()
        ffmpeg_process = None

        if not stop_event.is_set():
            print(
                f"FFmpeg exited with code {code}; restarting in 3s",
                flush=True,
            )
            await asyncio.sleep(3)


async def stop_all():
    stop_event.set()

    global ffmpeg_process
    if ffmpeg_process and ffmpeg_process.returncode is None:
        ffmpeg_process.terminate()
        try:
            await asyncio.wait_for(ffmpeg_process.wait(), 10)
        except asyncio.TimeoutError:
            ffmpeg_process.kill()
            await ffmpeg_process.wait()

    if live_call is not None:
        try:
            await client(functions.phone.DiscardGroupCallRequest(call=live_call))
        except Exception as exc:
            print(f"Live close error: {exc}", flush=True)


async def main():
    await client.start()
    me = await client.get_me()

    print(
        f"Telegram: id={me.id} username=@{me.username or '-'}",
        flush=True,
    )

    if SESSION_STRING:
        print(
            "Telegram session loaded from TG_SESSION_STRING",
            flush=True,
        )
    else:
        print(
            "WARNING: TG_SESSION_STRING is not set; interactive login may fail on Railway",
            flush=True,
        )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(stop_all()),
            )
        except NotImplementedError:
            pass

    task = asyncio.create_task(timer_writer())

    try:
        url, key = await start_live()
        print(
            "DEMOB RADIO Live Story active; starting FFmpeg",
            flush=True,
        )
        await stream(url, key)
    except RuntimeError as exc:
        print(f"STARTUP BLOCKED: {exc}", flush=True)
        raise
    finally:
        task.cancel()
        await stop_all()
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
