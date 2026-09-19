import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from .runtime import Runtime
from .config import Settings
from .contracts import Telemetry, InjectFault, ScenarioRequest
from .explanations import explain_incident

ROOT=Path(__file__).resolve().parents[1]

def create_app(settings=Settings(), runtime=None, start_background=True, mqtt_enabled=False):
    if settings.public_site and len(settings.operator_key) < 24:
        raise ValueError("Public deployment requires an OPERATOR_KEY of at least 24 characters")
    if settings.public_site and settings.mode != 'demo':
        raise ValueError("Public deployment currently supports simulated demo data only")

    @asynccontextmanager
    async def lifespan(app):
        app.state.runtime=runtime or Runtime(settings)
        r=app.state.runtime
        bridge=None
        if mqtt_enabled:
            if settings.mode!='external':
                raise ValueError('MQTT requires external mode')
            from .mqtt import MQTTBridge
            bridge=MQTTBridge(r)
            bridge.start()
        async def loop():
            while True:
                await asyncio.sleep(1)
                try:
                    def advance():
                        with r.lock:
                            if bridge:
                                bridge.drain()
                            r.tick()
                    await run_in_threadpool(advance)
                except Exception as exc:
                    r.error=type(exc).__name__+': '+str(exc)
                    with r.lock:
                        r.store.add('pipeline_error',{'error':r.error})
                    # Stop changing data after a broken pipeline; health reports the error.
                    break
        task=asyncio.create_task(loop()) if start_background else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if bridge:
                bridge.stop()
            if runtime is None:
                r.close()
    app=FastAPI(title='Unified PCB Assembly Digital Twin',version='1.0.0',lifespan=lifespan)

    def authorized(request):
        if not settings.public_site:
            return True
        authorization = request.headers.get('authorization', '')
        return secrets.compare_digest(authorization.encode(), ('Bearer '+settings.operator_key).encode())

    @app.middleware('http')
    async def protect_controls(request: Request, call_next):
        if request.url.path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS') and not authorized(request):
            return JSONResponse({'detail':'Operator access is required to change the shared demo or run scenarios.'}, status_code=401)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/access')
    def access(request: Request):
        return {'public':settings.public_site, 'can_control':authorized(request)}

    def get_runtime():
        return app.state.runtime

    @app.get('/')
    def index():
        return FileResponse(ROOT/'frontend/index.html')

    @app.get('/api/health')
    def health():
        r=get_runtime()
        return {'status':'error' if r.error else 'running','mode':r.settings.mode,
                'error':r.error,'last_tick_at':r.last_tick_at,'mqtt':r.mqtt_status}

    @app.get('/api/dashboard')
    def dashboard():
        return get_runtime().snapshot()

    @app.get('/api/line/topology')
    def topology():
        r=get_runtime()
        return {'stages':r.config.as_dict(),'production_order':['M1','M2','M3','M4','M5'],
                'routes':r.snapshot()['routes']}

    @app.get('/api/machines/{mid}')
    def machine(mid:str):
        for row in get_runtime().snapshot()['machines']:
            if row['machine_id']==mid:
                return row
        raise HTTPException(404,'Unknown machine')

    @app.post('/api/telemetry',status_code=202)
    def telemetry(record:Telemetry):
        try:
            return get_runtime().ingest(record)
        except ValueError as exc:
            raise HTTPException(409,str(exc))

    @app.post('/api/demo/fault/{mid}')
    def inject(mid:str,body:InjectFault):
        try:
            return get_runtime().inject(mid,body.fault_type)
        except ValueError as exc:
            raise HTTPException(409,str(exc))

    @app.post('/api/recovery/{mid}/correct')
    def correct(mid:str):
        try:
            return get_runtime().correct(mid)
        except ValueError as exc:
            raise HTTPException(409,str(exc))

    @app.post('/api/demo/reset')
    def reset():
        try:
            return get_runtime().reset_demo()
        except ValueError as exc:
            raise HTTPException(409,str(exc))

    @app.post('/api/scenarios/compare')
    def compare(body:ScenarioRequest):
        try:
            result=get_runtime().compare(body.machine_id,body.downtime_seconds,body.horizon_minutes,body.use_backup)
            with get_runtime().lock:
                get_runtime().store.add('whatif_compared',result)
            return result
        except ValueError as exc:
            raise HTTPException(409,str(exc))

    @app.get('/api/alerts/{decision_id}/explanation')
    def explanation(decision_id:str):
        r=get_runtime()
        with r.lock:
            try:
                return explain_incident(r,decision_id)
            except KeyError:
                raise HTTPException(404,'Unknown alert in this session')

    @app.get('/api/events')
    def events():
        r=get_runtime()
        with r.lock:
            return r.store.recent()

    @app.websocket('/ws/dashboard')
    async def dashboard_socket(ws:WebSocket):
        await ws.accept()
        try:
            while True:
                snapshot=await run_in_threadpool(get_runtime().snapshot)
                await ws.send_json(snapshot)
                await asyncio.sleep(1)
        except (WebSocketDisconnect,RuntimeError):
            pass

    app.mount('/static',StaticFiles(directory=ROOT/'frontend'),name='static')
    return app

