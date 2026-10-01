import asyncio
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
API_ID=int(os.environ["TG_API_ID"]); API_HASH=os.environ["TG_API_HASH"]
SESSION_STRING=os.getenv("TG_SESSION_STRING","").strip()
SESSION=os.getenv("TG_SESSION","demob_user")
DEMOB_DATE=os.getenv("DEMOB_DATE","2026-10-15T00:00:00+03:00")
TZ=ZoneInfo(os.getenv("TZ","Europe/Moscow"))
CAPTION=os.getenv("LIVE_CAPTION","🔥 ФИНИШНАЯ ПРЯМАЯ — СЧЁТЧИК ДО ДЕМБЕЛЯ")
WIDTH=int(os.getenv("VIDEO_WIDTH","1280")); HEIGHT=int(os.getenv("VIDEO_HEIGHT","720"))
FPS=int(os.getenv("VIDEO_FPS","30")); BITRATE=os.getenv("VIDEO_BITRATE","1200k")
PRESET=os.getenv("VIDEO_PRESET","veryfast")
DATA=Path("data"); RUNTIME=Path("runtime"); DATA.mkdir(exist_ok=True); RUNTIME.mkdir(exist_ok=True)
TIMER_FILE=RUNTIME/"timer.txt"

if SESSION_STRING:
    client=TelegramClient(StringSession(SESSION_STRING),API_ID,API_HASH)
else:
    client=TelegramClient(str(DATA/SESSION),API_ID,API_HASH)

ffmpeg_process=None; live_call=None; stop_event=asyncio.Event()

def demob_dt():
    dt=datetime.fromisoformat(DEMOB_DATE)
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)

def format_remaining():
    s=max(0,int((demob_dt()-datetime.now(demob_dt().tzinfo)).total_seconds()))
    d,s=divmod(s,86400); h,s=divmod(s,3600); m,s=divmod(s,60)
    return f"{d:02d} ДНЕЙ  {h:02d}:{m:02d}:{s:02d}"

def write_timer():
    tmp=TIMER_FILE.with_suffix(".tmp"); tmp.write_text(format_remaining(),encoding="utf-8"); tmp.replace(TIMER_FILE)

def find_call(obj):
    if isinstance(obj,types.InputGroupCall): return obj
    if isinstance(obj,types.MessageMediaVideoStream): return obj.call
    if isinstance(obj,(list,tuple)):
        for x in obj:
            r=find_call(x)
            if r:return r
    if hasattr(obj,"__dict__"):
        for x in vars(obj).values():
            r=find_call(x)
            if r:return r
    return None

def ffmpeg_cmd(url,key):
    out=f"{url.rstrip('/')}/{key}"
    vf=("drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "text='ДО ДЕМБЕЛЯ':fontcolor=white:fontsize=70:x=(w-text_w)/2:y=150,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "textfile=/app/runtime/timer.txt:reload=1:fontcolor=white:fontsize=82:x=(w-text_w)/2:y=260,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "text='15.10.2026':fontcolor=white:fontsize=40:x=(w-text_w)/2:y=390,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "text='ФИНИШНАЯ ПРЯМАЯ':fontcolor=#b2fa72:fontsize=44:x=(w-text_w)/2:y=510")
    return ["ffmpeg","-hide_banner","-loglevel","warning","-re","-f","lavfi","-i",f"color=c=#090c10:s={WIDTH}x{HEIGHT}:r={FPS}",
            "-f","lavfi","-i","anullsrc=channel_layout=stereo:sample_rate=44100","-vf",vf,
            "-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset",PRESET,"-tune","zerolatency",
            "-pix_fmt","yuv420p","-r",str(FPS),"-g",str(FPS*2),"-b:v",BITRATE,"-maxrate",BITRATE,"-bufsize","3M",
            "-c:a","aac","-b:a","96k","-ar","44100","-ac","2","-f","flv",out]

async def timer_writer():
    while not stop_event.is_set():
        write_timer()
        try: await asyncio.wait_for(stop_event.wait(),timeout=1)
        except asyncio.TimeoutError: pass

async def start_live():
    global live_call
    peer=await client.get_input_entity("me")
    result=await client(functions.stories.StartLiveRequest(
        peer=peer,rtmp_stream=True,pinned=False,noforwards=False,caption=CAPTION,
        privacy_rules=[types.InputPrivacyValueAllowAll()],
        random_id=random.randint(1,2**63-1),messages_enabled=True))
    live_call=find_call(result)
    if live_call is None:
        stories=await client(functions.stories.GetPeerStoriesRequest(peer=peer))
        for item in stories.stories:
            if isinstance(getattr(item,"media",None),types.MessageMediaVideoStream):
                live_call=item.media.call; break
    if live_call is None: raise RuntimeError("InputGroupCall не найден после stories.startLive")
    creds=await client(functions.phone.GetGroupCallStreamRtmpUrlRequest(peer=peer,revoke=False,live_story=True))
    return creds.url,creds.key

async def stream(url,key):
    global ffmpeg_process
    while not stop_event.is_set():
        write_timer()
        ffmpeg_process=await asyncio.create_subprocess_exec(*ffmpeg_cmd(url,key))
        code=await ffmpeg_process.wait(); ffmpeg_process=None
        if not stop_event.is_set():
            print(f"FFmpeg exited {code}; restarting",flush=True); await asyncio.sleep(3)

async def stop_all():
    stop_event.set()
    global ffmpeg_process
    if ffmpeg_process and ffmpeg_process.returncode is None:
        ffmpeg_process.terminate()
        try: await asyncio.wait_for(ffmpeg_process.wait(),10)
        except asyncio.TimeoutError: ffmpeg_process.kill(); await ffmpeg_process.wait()
    if live_call is not None:
        try: await client(functions.phone.DiscardGroupCallRequest(call=live_call))
        except Exception as e: print(f"Live close error: {e}",flush=True)

async def main():
    await client.start(); me=await client.get_me()
    print(f"Telegram: id={me.id} username=@{me.username or '-'}",flush=True)
    if SESSION_STRING:
        print("Telegram session loaded from TG_SESSION_STRING",flush=True)
    else:
        print("WARNING: TG_SESSION_STRING is not set; interactive login may fail on Railway",flush=True)
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        try: loop.add_signal_handler(sig,lambda:asyncio.create_task(stop_all()))
        except NotImplementedError: pass
    task=asyncio.create_task(timer_writer())
    try:
        url,key=await start_live(); print("Live Story active; starting FFmpeg",flush=True); await stream(url,key)
    finally:
        task.cancel(); await stop_all(); await client.disconnect()

if __name__=="__main__": asyncio.run(main())
