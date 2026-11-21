"""Application factory. Run with:  uvicorn app.main:create_app --factory"""
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .config import Settings
from .db import make_engine, make_sessionmaker
from .peer import PeerClient
from .routers import auth, insights, internal, operations, users
from .services.auth import RateLimiter
from .services.sync_worker import SyncRunner, clear_standalone_queue
from .store import set_standalone
from .store import ensure_defaults
from .util import AppError

log = logging.getLogger("dispensary")


_FRIENDLY = {
    "username": "Username must be 3–40 characters: lowercase letters, numbers, dot or underscore (no spaces).",
    "mobile": "Enter a valid mobile number of 10 digits, e.g. 9876543210 or +91 98765 43210.",
    "full_name": "Enter the full name (at least 2 characters).",
    "email": "Enter a valid email address, e.g. name@gmail.com, or leave it empty.",
}


def _validation_message(errors) -> str:
    first = errors[0] if errors else {}
    field = str(first.get("loc", [""])[-1]) if first.get("loc") else ""
    if field in _FRIENDLY:
        return _FRIENDLY[field]
    loc = ".".join(str(p) for p in first.get("loc", []) if p not in ("body",))
    return f"{loc}: {first.get('msg', 'invalid value')}" if loc else first.get("msg", "Invalid request.")


def create_app(settings: Settings | None = None, *, peer_client: httpx.Client | None = None,
               start_worker: bool | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    engine = make_engine(settings.database_url)
    SessionLocal = make_sessionmaker(engine)
    peer = PeerClient(settings, peer_client)
    set_standalone(settings.is_standalone)
    run_worker = settings.is_hospital and (settings.run_sync_worker if start_worker is None else start_worker)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            ensure_defaults(SessionLocal)
        except Exception:
            log.exception("Could not initialise defaults — have migrations been applied? (alembic upgrade head)")
        if settings.is_standalone:
            try:
                clear_standalone_queue(SessionLocal)
            except Exception:
                log.exception("Could not clear the old sync queue")
        if app.state.runner:
            app.state.runner.start()
        yield
        if app.state.runner:
            app.state.runner.stop()
        engine.dispose()

    app = FastAPI(title=f"Dispensary Desk API ({settings.app_role})", version="1.0.0", lifespan=lifespan,
                  docs_url="/api/docs" if settings.environment != "production" else None,
                  openapi_url="/api/openapi.json" if settings.environment != "production" else None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = SessionLocal
    app.state.peer = peer
    app.state.limiter = RateLimiter()
    app.state.ping_cache = {}
    app.state.runner = SyncRunner(settings, SessionLocal, peer) if run_worker else None

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message, **exc.extra}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _req_validation(_: Request, exc: RequestValidationError):
        return JSONResponse({"error": {"code": "VALIDATION", "message": _validation_message(exc.errors())}}, status_code=422)

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError):
        return JSONResponse({"error": {"code": "VALIDATION", "message": _validation_message(exc.errors())}}, status_code=422)

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                           allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    for router in (auth.router, operations.router, insights.router, users.router):
        app.include_router(router)
    app.include_router(internal.hospital if settings.is_hospital else internal.cloud)
    if settings.static_dir:
        _serve_web_app(app, settings.static_dir)
    return app


def _serve_web_app(app: FastAPI, static_dir: str) -> None:
    """Serve the built React app (desktop install): real files as-is, every other non-API path -> index.html."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    root = Path(static_dir).resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    async def _web(path: str):
        if path.startswith("api/") or path == "api":
            return JSONResponse({"error": {"code": "NOT_FOUND", "message": "Not found."}}, status_code=404)
        target = (root / path).resolve()
        if path and target.is_file() and target.is_relative_to(root):
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith("assets/") else None
            return FileResponse(target, headers=headers)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
