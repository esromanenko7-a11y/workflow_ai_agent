import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from app.observability.logging import setup_logging
import time
import uuid
import secrets
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.exceptions import LLMError, LLMRateLimitError, LLMTimeoutError
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.routers.models import router as models_router

from app.observability.tracing import setup_tracing


settings = get_settings()
setup_logging(settings.log_level)
logger = structlog.get_logger("llm-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    logger.info("service_starting")

    app.state.canary = f"CANARY_{secrets.token_hex(4)}"
    logger.info("security_canary_initialized")

    # Важно: tracing настраиваем ДО создания AsyncOpenAI-клиента.
    # Так OpenAIInstrumentor успеет подключиться к OpenAI SDK.
    setup_tracing(project_name="diploma-fastapi")

    # trust_env=False нужен, чтобы локальная Ollama не пыталась ходить через VPN/proxy.
    app.state.http_client = httpx.AsyncClient(
        trust_env=False,
        timeout=settings.llm.request_timeout,
    )



    app.state.openai_client = AsyncOpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.openai_base_url,
        timeout=settings.llm.request_timeout,
        http_client=app.state.http_client,
    )

    # Redis-кеш не должен блокировать основной сценарий, поэтому ставим короткие timeout.
    app.state.cache = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )

    try:
        yield
    finally:
        logger.info("service_stopping")

        await app.state.openai_client.close()

        if getattr(app.state, "http_client", None) is not None:
            await app.state.http_client.aclose()

        if getattr(app.state, "cache", None) is not None:
            await app.state.cache.aclose()

app = FastAPI(
    title="Data Package Validation Assistant",
    description="FastAPI-сервис для ИИ-ассистента проверки пакетов с данными",
    version="0.1.0",
    lifespan=lifespan,
)
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    user_id = request.headers.get("X-User-ID")

    request.state.request_id = request_id

    clear_contextvars()
    bind_contextvars(
        request_id=request_id,
        user_id=user_id,
        method=request.method,
        path=request.url.path,
    )

    started_at = time.perf_counter()

    logger.info("http_request_started")

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

        logger.exception(
            "http_request_failed",
            status_code=500,
            duration_ms=duration_ms,
        )

        clear_contextvars()
        raise

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

    response.headers["X-Request-ID"] = request_id

    logger.info(
        "http_request_completed",
        status_code=response.status_code,
        duration_ms=duration_ms,
    )

    clear_contextvars()

    return response

@app.exception_handler(LLMError)
async def handle_llm_error(request: Request, exc: LLMError) -> JSONResponse:
    if isinstance(exc, LLMRateLimitError):
        status_code = 429
    elif isinstance(exc, LLMTimeoutError):
        status_code = 504
    else:
        status_code = 502

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    details = []

    for error in exc.errors():
        field_path = ".".join(str(part) for part in error.get("loc", []))
        details.append(
            {
                "field": field_path,
                "message": error.get("msg", "Ошибка валидации"),
            }
        )

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Ошибка валидации запроса",
                "details": details,
            }
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.include_router(health_router)
app.include_router(models_router)
app.include_router(chat_router)