"""
FootIntel Phase 3 — FastAPI REST Backend Entrypoint.
Run from backend/:
    uvicorn api.main:app --reload
"""

import logging
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import API_DESCRIPTION, API_TITLE, API_VERSION, get_cors_origins
from api.routes import domestic, health, market_value, overview, players, statistics, trends, ucl

logger = logging.getLogger("footintel.api")


def create_app() -> FastAPI:
    """Create and configure the FootIntel FastAPI application."""
    application = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        return response

    @application.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "http_error",
                "detail": exc.detail,
                "status_code": exc.status_code,
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        status_code = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
        return JSONResponse(
            status_code=status_code,
            content={
                "error": "validation_error",
                "detail": exc.errors(),
                "status_code": status_code,
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server error during %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_server_error",
                "detail": "An internal server error occurred.",
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
        )

    application.include_router(health.router)
    application.include_router(overview.router)
    application.include_router(trends.router)
    application.include_router(domestic.router)
    application.include_router(ucl.router)
    application.include_router(market_value.router)
    application.include_router(statistics.router)
    application.include_router(players.router)

    @application.get("/", tags=["Root"], summary="API Root Metadata")
    def root() -> dict[str, object]:
        return {
            "name": API_TITLE,
            "version": API_VERSION,
            "docs_url": "/docs",
            "openapi_url": "/openapi.json",
            "endpoints": {
                "health": "/health",
                "overview": "/api/v1/overview",
                "trends": "/api/v1/trends",
                "domestic": "/api/v1/domestic",
                "ucl": "/api/v1/ucl",
                "ucl_paired": "/api/v1/ucl/paired",
                "market_value_summary": "/api/v1/market-value/summary",
                "market_value_transfers": "/api/v1/market-value/transfers",
                "market_value_player_gains": "/api/v1/market-value/player-gains",
                "statistics": "/api/v1/statistics",
                "players_search": "/api/v1/players/search",
                "players_compare": "/api/v1/players/compare",
                "player_detail": "/api/v1/players/{player_id}",
                "player_transfer_spells": "/api/v1/players/{player_id}/transfer-spells",
            },
        }

    return application


app = create_app()
