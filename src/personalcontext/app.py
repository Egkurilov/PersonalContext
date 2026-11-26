from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from personalcontext.jobs.scheduler import Scheduler
from personalcontext.storage.initialize import initialize_database


def create_app(database_path: Path, web_root: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize_database(database_path)
        scheduler = Scheduler(database_path, {})
        try:
            await scheduler.start()
        except BaseException:
            await scheduler.stop()
            raise
        app.state.scheduler = scheduler
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            await scheduler.stop()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def restrict_local_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.client is None or request.client.host != "127.0.0.1":
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
        if request.headers.get("host") not in {"127.0.0.1:17890", "127.0.0.1"}:
            return JSONResponse({"detail": "Invalid host"}, status_code=400)
        origin = request.headers.get("origin")
        if origin is not None and origin != "http://127.0.0.1:17890":
            return JSONResponse({"detail": "Invalid origin"}, status_code=403)
        return await call_next(request)

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", response_model=None)
    async def ready() -> dict[str, str] | JSONResponse:
        if not getattr(app.state, "ready", False) or app.state.scheduler.task.done():
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ready"}

    if web_root is not None:
        app.mount("/assets", StaticFiles(directory=web_root / "assets"), name="assets")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(web_root / "index.html")

    return app
