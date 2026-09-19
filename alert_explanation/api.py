"""Optional HTTP adapter. Run: python -m uvicorn alert_explanation.api:app"""
import asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from .models import AlertInput, Explanation
from .service import explain_alert

MAX_BODY_BYTES = 256 * 1024


def create_app(orderer=None):
    app = FastAPI(title="Manufacturing Alert Explanations", version="1.0.0",
                  description="Evidence-bound explanations. No machine control or autonomous diagnosis.")

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        if request.method == "POST":
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BODY_BYTES:
                    return JSONResponse(status_code=413, content={"error": "Request exceeds 256 KiB"})
                chunks.append(chunk)
            request._body = b"".join(chunks)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(status_code=422, content={
            "error": "Invalid backend evidence",
            "details": [{"location": list(e["loc"]), "message": e["msg"], "type": e["type"]} for e in exc.errors()]
        })

    @app.get("/health")
    def health():
        return {"status": "ok", "ai_provider_configured": orderer is not None, "machine_control": False}

    @app.post("/api/alerts/explain", response_model=Explanation)
    async def explain(payload: AlertInput):
        return await asyncio.to_thread(explain_alert, payload, orderer)

    @app.get("/api/alerts/explanation-schema")
    def schema():
        return Explanation.model_json_schema()

    return app


app = create_app()

