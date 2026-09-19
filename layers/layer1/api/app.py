"""
Optional FastAPI interface exposing Layer 1's output to Layer 2 / Layer 3.
This is NOT a dashboard - it is a clean programmatic read interface plus a
WebSocket for continuous production data, so downstream layers have a
well-defined way to consume both streams (and their fused state) without
assuming MQTT for Stream B.
"""
import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from layers.layer1.common.logger import get_logger
from layers.layer1.config import config

log = get_logger("api")

app = FastAPI(title="Layer 1 - Data Acquisition & Real-Time Communication")

# Wired in by main.py at startup
_consumer = None
_machine_provider = None
_state_manager = None
_ws_clients = []
_loop = None


def wire(consumer, machine_provider, state_manager):
    global _consumer, _machine_provider, _state_manager
    _consumer = consumer
    _machine_provider = machine_provider
    _state_manager = state_manager
    _machine_provider.subscribe(_broadcast_production)


def _broadcast_production(record: dict):
    """Push new production records to any connected WebSocket clients."""
    if not _ws_clients or _loop is None:
        return
    payload = json.dumps(record)
    for ws in list(_ws_clients):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(payload), _loop)
        except Exception:
            pass


@app.on_event("startup")
async def _capture_loop():
    global _loop
    _loop = asyncio.get_event_loop()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/machines")
def list_machines():
    return {"machines": config.MACHINES, "names": config.MACHINE_NAMES}


@app.get("/sensors/latest")
def sensors_latest():
    return _consumer.get_latest() if _consumer else {}


@app.get("/sensors/{machine_id}/latest")
def sensor_latest(machine_id: str):
    return _consumer.get_latest(machine_id) if _consumer else {}


@app.get("/production/latest")
def production_latest():
    return _machine_provider.get_latest_state() if _machine_provider else {}


@app.get("/production/{machine_id}/latest")
def production_machine_latest(machine_id: str):
    return _machine_provider.get_latest_state(machine_id) if _machine_provider else {}


@app.get("/state")
def fused_state_all():
    return _state_manager.get_fused_state() if _state_manager else {}


@app.get("/state/{machine_id}")
def fused_state(machine_id: str):
    return _state_manager.get_fused_state(machine_id) if _state_manager else {}


@app.websocket("/ws/production")
async def ws_production(websocket: WebSocket):
    """Continuous live feed of Stream B (machine/production) records."""
    await websocket.accept()
    _ws_clients.append(websocket)
    log.info("WebSocket client connected to /ws/production")
    try:
        while True:
            await websocket.receive_text()  # keep-alive; client pings are ignored
    except WebSocketDisconnect:
        _ws_clients.remove(websocket)
        log.info("WebSocket client disconnected")
