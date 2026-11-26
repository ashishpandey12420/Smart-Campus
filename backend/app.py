"""FastAPI application: API routers + the built React single-page app."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ALLOW_EMBED, API_PREFIX, APP_NAME, APP_VERSION, CORS_ORIGINS, STATIC_DIR
from .database import Base, SessionLocal, engine
from .routers import admin, attendance, auth, dashboard, faculty, reference, students, system
from .seed import seed_initial

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("smartcampus")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_initial(db)
    finally:
        db.close()
    log.info("%s %s ready (db=%s)", APP_NAME, APP_VERSION, engine.dialect.name)
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title=f"{APP_NAME} API",
        version=APP_VERSION,
        description="Student & Faculty Management System — REST API",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    application.add_middleware(GZipMiddleware, minimum_size=1024)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if ALLOW_EMBED:
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; connect-src 'self'; font-src 'self' data:; frame-ancestors *",
            )
        else:
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; connect-src 'self'; font-src 'self' data:; frame-ancestors 'self'",
            )
        return response

    for module in (auth, students, faculty, reference, attendance, dashboard, admin, system):
        application.include_router(module.router, prefix=API_PREFIX)

    @application.get(f"{API_PREFIX}/health", tags=["system"])
    def health():
        return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}

    # ---- static SPA ----
    assets = STATIC_DIR / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="assets")

    @application.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "api")):
            raise HTTPException(404, "Not found")
        candidate = (STATIC_DIR / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(STATIC_DIR.resolve())):
            return FileResponse(candidate)
        index = STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            {
                "detail": "Frontend build not found.",
                "fix": "cd frontend && npm install && npm run build",
            },
            status_code=503,
        )

    return application


app = create_app()
