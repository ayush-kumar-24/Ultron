"""FastAPI app factory, uvicorn thread runner, and lifespan."""

from __future__ import annotations

import threading

from loguru import logger

from maira.app.container import Container
from maira.app.lifecycle import Lifecycle
from maira.app.settings import Settings
from maira.api.deps import bind_container
from maira.shared.utils.paths import project_root


def _ensure_api() -> tuple[bool, str]:
  try:
    import fastapi  # noqa: F401
    import uvicorn  # noqa: F401
  except ImportError:
    return False, 'install the API extra: pip install -e ".[api]"'
  return True, "ready"


def create_app(container: Container):
  """Build the FastAPI app bound to a live (or test) container."""
  from fastapi import FastAPI, HTTPException, Request
  from fastapi.exceptions import RequestValidationError
  from fastapi.middleware.cors import CORSMiddleware
  from fastapi.responses import JSONResponse
  from fastapi.staticfiles import StaticFiles
  from starlette.exceptions import HTTPException as StarletteHTTPException

  from maira.api.routes import chat, memory, settings as settings_routes, system, user

  bind_container(container)
  settings: Settings = container.resolve("settings")

  app = FastAPI(title="Ultron API", version="0.1.0", docs_url=None, redoc_url=None)

  origins = list(settings.api.cors_origins) if settings.api.cors_origins else ["*"]
  app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
  )

  app.include_router(system.router, prefix="/api")
  app.include_router(user.router, prefix="/api")
  app.include_router(settings_routes.router, prefix="/api")
  app.include_router(chat.router, prefix="/api")
  app.include_router(memory.router, prefix="/api")

  @app.api_route("/api/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"])
  def not_built(path: str) -> JSONResponse:
    return JSONResponse({"detail": f"Not implemented: /api/{path}"}, status_code=404)

  @app.exception_handler(RequestValidationError)
  async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse({"detail": "Invalid request"}, status_code=422)

  @app.exception_handler(StarletteHTTPException)
  async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Not found"
    return JSONResponse({"detail": detail}, status_code=exc.status_code)

  @app.exception_handler(Exception)
  async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
      raise exc
    logger.exception("API error: {}", exc)
    return JSONResponse({"detail": "Ultron hit an internal error"}, status_code=500)

  frontend_dir = project_root() / "frontend"
  if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

  return app


def start_api_thread(app, settings: Settings, lifecycle: Lifecycle) -> threading.Thread:
  """Run uvicorn in a daemon thread so Qt keeps the main loop."""
  ok, reason = _ensure_api()
  if not ok:
    logger.warning("HTTP API not started ({})", reason)
    return threading.Thread(target=lambda: None)

  import uvicorn

  config = uvicorn.Config(
    app,
    host=settings.api.host,
    port=settings.api.port,
    log_level="info",
    lifespan="on",
  )
  server = uvicorn.Server(config)

  def _run() -> None:
    logger.info("HTTP API listening on http://{}:{}", settings.api.host, settings.api.port)
    server.run()

  thread = threading.Thread(target=_run, name="ultron-api", daemon=True)
  lifecycle.on_shutdown(lambda: setattr(server, "should_exit", True))
  thread.start()
  return thread


def serve_api(app, settings: Settings, lifecycle: Lifecycle) -> None:
  """Block the current thread on uvicorn (headless mode)."""
  ok, reason = _ensure_api()
  if not ok:
    logger.error("Cannot serve API ({})", reason)
    raise SystemExit(1)

  import uvicorn

  logger.info("HTTP API listening on http://{}:{}", settings.api.host, settings.api.port)
  try:
    uvicorn.run(app, host=settings.api.host, port=settings.api.port, log_level="info")
  finally:
    lifecycle.run_shutdown()
