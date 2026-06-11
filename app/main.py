import logging
import time
import uuid
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


settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO)
)
logger = logging.getLogger("llm-service")


@asynccontextmanager
async def lifespan(app: FastAPI):


    logger.info("Starting FastAPI LLM service")

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
        logger.info("Stopping FastAPI LLM service")

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
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
    request.state.request_id = request_id

    started_at = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

        logger.exception(
            "request failed request_id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            500,
            duration_ms,
        )
        raise

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

    response.headers["X-Request-ID"] = request_id

    logger.info(
        "request completed request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )

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