import asyncio
import json
import os
import time
from typing import Any, Dict, Set, Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.dirname(APP_DIR)  # = .../mnt/data

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Простая шина событий ----
class EventBus:
    def __init__(self):
        self.queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self.clients: Set[WebSocket] = set()

    async def publish(self, event: Dict[str, Any]):
        await self.queue.put(event)

event_bus = EventBus()

async def broadcaster():
    while True:
        event = await event_bus.queue.get()
        payload = json.dumps(event, ensure_ascii=False)
        to_remove = []
        for ws in list(event_bus.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            event_bus.clients.discard(ws)

@app.on_event("startup")
async def startup():
    asyncio.create_task(broadcaster())

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    event_bus.clients.add(ws)
    try:
        while True:
            # можно принимать команды из клиента (пока не используем)
            await ws.receive_text()
    except WebSocketDisconnect:
        event_bus.clients.discard(ws)

# ---- Менеджер подпроцесса ----
class ProcessManager:
    def __init__(self):
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.reader_task: Optional[asyncio.Task] = None
        self.current_script: Optional[str] = None

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def start(self, script_path: str, args: Optional[List[str]] = None):
        if self.is_running():
            raise RuntimeError("A script is already running")
        if not os.path.isfile(script_path):
            raise FileNotFoundError(f"Script not found: {script_path}")
        args = args or []
        self.current_script = os.path.basename(script_path)
        # запускаем тем же интерпретатором, с unbuffered выводом
        self.proc = await asyncio.create_subprocess_exec(
            "python",
            script_path,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=DATA_DIR,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        async def _reader():
            assert self.proc is not None
            while True:
                if self.proc.stdout is None:
                    break
                line = await self.proc.stdout.readline()
                if not line:
                    break
                try:
                    text = line.decode("utf-8", "replace").rstrip("\n")
                except Exception:
                    text = str(line)
                await event_bus.publish({
                    "type": "stdout",
                    "script": self.current_script,
                    "line": text,
                    "ts": time.time()
                })
            rc = await self.proc.wait()
            await event_bus.publish({
                "type": "exit",
                "script": self.current_script,
                "returncode": rc,
                "ts": time.time()
            })

        self.reader_task = asyncio.create_task(_reader())

    async def stop(self):
        if not self.is_running():
            return
        assert self.proc is not None
        self.proc.terminate()
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            self.proc.kill()
            await self.proc.wait()
        self.proc = None
        self.current_script = None
        if self.reader_task:
            self.reader_task.cancel()
            self.reader_task = None

proc_manager = ProcessManager()

# ---- REST эндпоинты ----
@app.get("/scripts")
async def list_scripts():
    # список .py в /mnt/data
    entries = []
    for name in os.listdir(DATA_DIR):
        if name.endswith(".py"):
            entries.append(name)
    return {"scripts": sorted(entries)}

@app.get("/status")
async def status():
    return {
        "running": proc_manager.is_running(),
        "script": proc_manager.current_script
    }

@app.post("/start")
async def start(payload: Dict[str, Any]):
    script = payload.get("script")
    args = payload.get("args", [])
    if not script or not isinstance(script, str):
        raise HTTPException(400, "Missing 'script'")
    script_path = os.path.join(DATA_DIR, script)
    try:
        await proc_manager.start(script_path, args=args)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "script": script}

@app.post("/stop")
async def stop():
    await proc_manager.stop()
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )