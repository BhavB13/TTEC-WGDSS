# app/main.py

from contextlib import asynccontextmanager
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.dashboard import router as dashboard_router
from app.api.storm import router as storm_router
from app.api.router import api_router
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.database.init_db import initialize_database
from app.services.calibration_import_service import CalibrationImportService

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.APP_NAME)
    if settings.DATABASE_AUTO_CREATE:
        initialize_database()

    if settings.CALIBRATION_AUTO_IMPORT and settings.CALIBRATION_DATA_ZIP_PATH:
        import_service = CalibrationImportService()
        try:
            import_service.import_archive_if_present(settings.CALIBRATION_DATA_ZIP_PATH)
        except Exception:  # pragma: no cover - startup resilience
            logger.exception("Calibration import skipped")
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Weather-Based Generation Decision Support System",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled request error",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path},
        )
        raise
    duration_ms = round((perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "Request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response

app.include_router(
    api_router,
    prefix=settings.API_V1_PREFIX,
)

app.include_router(
    dashboard_router,
    prefix="/api",
    tags=["dashboard"],
)

app.include_router(
    storm_router,
    prefix="/api",
    tags=["storm"],
)


@app.get("/", tags=["root"])
async def root():
    return {
        "application": settings.APP_NAME,
        "version": "0.1.0",
        "status": "running",
    }
