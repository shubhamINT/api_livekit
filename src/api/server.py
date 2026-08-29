import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from src.api.routes import (
    auth,
    health,
    assistant,
    audio,
    sip,
    call,
    tool,
    logs,
    web_call,
    inbound,
    inbound_context_strategy,
    analytics,
    admin,
)
from starlette.routing import Route
from src.api.mcp_docs import asgi_app as docs_mcp_asgi, mcp as docs_mcp
from src.core.logger import setup_logging, logger
from src.core.version import __version__
from src.core.db.database import init_db, close_db
from src.api.models.response_models import apiResponse

# Setup logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    # Startup
    await init_db()

    dispatcher_task = None

    # ENABLE_SIP_LISTENER / ENABLE_DISPATCHER default to "true" so existing single-container
    # setups (dev, local) keep working without any env changes.
    # In production, the dedicated sip_dispatcher container sets both to "true" and the
    # api container sets both to "false" — preventing port conflicts and duplicate dispatch.
    if os.getenv("ENABLE_SIP_LISTENER", "true").lower() == "true":
        from src.services.exotel.custom_sip_reach.inbound_listener import (
            ensure_inbound_server,
        )

        await ensure_inbound_server()

    if os.getenv("ENABLE_DISPATCHER", "true").lower() == "true":
        from src.services.outbound_dispatcher import outbound_dispatcher_loop

        dispatcher_task = asyncio.create_task(outbound_dispatcher_loop())

    # Starlette does not propagate lifespan into mounted sub-apps, so the MCP
    # streamable-HTTP session manager has to be started here or /mcp 500s.
    async with docs_mcp.session_manager.run():
        yield

    # Shutdown
    if dispatcher_task is not None:
        dispatcher_task.cancel()
    await close_db()


app = FastAPI(title="LiveKit AI Backend", version=__version__, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    from fastapi.encoders import jsonable_encoder

    from src.core.providers.keys import redact_validation_errors

    # Clean up errors to ensure they are JSON serializable, then strip the submitted
    # values: both `exc.errors()[].input` and `str(exc)` echo the rejected value, which
    # for an `api_key` field means handing the caller's secret back in the 422 body and
    # writing it to the log. Build the message from `loc`/`msg` only, never `str(exc)`.
    errors = redact_validation_errors(jsonable_encoder(exc.errors()))

    error_msg = "; ".join(
        f"{'.'.join(str(part) for part in error.get('loc', ()))}: {error.get('msg', '')}"
        for error in errors
    )

    # Check for JSON invalid errors to provide better hints
    for error in errors:
        if error.get("type") == "json_invalid":
            ctx = error.get("ctx", {})
            if "Invalid control character" in str(ctx.get("error", "")):
                error_msg += ". Hint: Literal newlines and unescaped quotes are not allowed in JSON strings. If you are pasting a YAML prompt, Please store it in a variable and send it in the request."
            elif "Expecting value" in str(ctx.get("error", "")):
                error_msg += ". Hint: The JSON body is malformed or incomplete."

    # Log detailed error
    logger.error(f"Validation Error: {error_msg}")

    return JSONResponse(
        status_code=422,
        content=apiResponse(
            success=False,
            message=f"Validation Error: {error_msg}",
            data={"errors": errors},
        ).model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    from src.core.providers.keys import redact_text

    # Route handlers raise details that may embed a caught exception's text (which
    # can carry a secret), so scrub before it reaches the body.
    return JSONResponse(
        status_code=exc.status_code,
        content=apiResponse(
            success=False, message=redact_text(str(exc.detail)), data={}
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    import traceback

    from src.core.providers.keys import redact_text

    trace = traceback.format_exc()
    logger.error(f"Generic Error: {trace}")

    # Never echo str(exc) back to the caller — third-party SDK / DB error text can
    # contain the submitted api_key. The full trace is logged above; the client only
    # sees a redacted fragment.
    return JSONResponse(
        status_code=500,
        content=apiResponse(
            success=False, message=f"Internal Server Error: {redact_text(str(exc))}", data={}
        ).model_dump(),
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(health.router, tags=["Health"])
app.include_router(assistant.router, prefix="/assistant", tags=["Assistant"])
app.include_router(audio.router, prefix="/audio", tags=["Audio"])
app.include_router(sip.router, prefix="/sip", tags=["Outbound SIP"])
app.include_router(call.router, prefix="/call", tags=["Call"])
app.include_router(tool.router, prefix="/tool", tags=["Tool"])
app.include_router(logs.router, prefix="/logs", tags=["Logs"])
app.include_router(web_call.router, prefix="/web_call", tags=["Web Call"])
app.include_router(inbound.router, prefix="/inbound", tags=["Inbound Call"])
app.include_router(
    inbound_context_strategy.router,
    prefix="/inbound_context_strategy",
    tags=["Inbound Context Strategy"],
)
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

# Serve MkDocs documentation site
site_dir = Path(__file__).resolve().parents[2] / "site"
if site_dir.exists():
    app.mount(
        "/documentation",
        StaticFiles(directory=str(site_dir), html=True),
        name="documentation",
    )

# Serve the same documentation to AI agents over MCP (streamable HTTP).
app.router.routes.append(Route("/mcp", endpoint=docs_mcp_asgi, name="mcp_docs"))

if __name__ == "__main__":
    import uvicorn
    from src.core.config import settings

    uvicorn.run(
        "src.api.server:app", host="0.0.0.0", port=int(settings.PORT), reload=True
    )
