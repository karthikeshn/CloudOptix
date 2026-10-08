from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
import logging

from app.core.config import settings
from app.core.database import init_db
from app.monitoring.state_monitor import recover_orphaned_transitions
from app.core.scheduler import run_control_scheduler
from app.api import cloud_config, control, inventory, notifications, auth

logger = logging.getLogger(__name__)

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.args and len(record.args) >= 3 and not any(
            x in record.args[2] for x in ("/sync-status", "/notifications")
        )

# Filter out frequent polling from uvicorn access logs
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database and background scheduler...")
    await init_db()
    await recover_orphaned_transitions()
    asyncio.create_task(run_control_scheduler())
    yield

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception at {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "An internal server error occurred."}
    )

app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(cloud_config.router, prefix=settings.API_V1_STR)
app.include_router(control.router, prefix=settings.API_V1_STR)
app.include_router(inventory.router, prefix=settings.API_V1_STR)
app.include_router(notifications.router, prefix=settings.API_V1_STR)

@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "service": settings.APP_NAME}
