import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from personalcontext.audit.http_routes import router as audit_router
from personalcontext.audit.retention import AuditHousekeeping
from personalcontext.auth.http_routes import router as auth_router
from personalcontext.auth.owner_bootstrap import OwnerBootstrap
from personalcontext.auth.owner_login import OwnerLogin
from personalcontext.auth.password_executor import PasswordExecutor
from personalcontext.auth.rotation_http import router as rotation_router
from personalcontext.contracts.health import HealthResponse, ReadinessResponse
from personalcontext.demo.seed import DemoResponse, seed_demo
from personalcontext.devices.device_http import router as device_access_router
from personalcontext.devices.extension_http import router as extension_router
from personalcontext.devices.http_routes import router as device_router
from personalcontext.jobs.scheduler import Scheduler
from personalcontext.mcp_auth.http import router as mcp_auth_router
from personalcontext.network.firewall.http import router as firewall_router
from personalcontext.network.middleware import restrict_requests
from personalcontext.network.protocols.websocket import RejectWebSockets
from personalcontext.network.settings_http import router as private_settings_router
from personalcontext.privacy.http_routes import router as privacy_router
from personalcontext.privacy.preview_routes import router as preview_router
from personalcontext.privacy.runtime.latch import CaptureLatch
from personalcontext.sources.config_http import router as config_router
from personalcontext.sources.http_routes import router as sources_router
from personalcontext.storage.initialize import initialize_database


def create_app(database_path: Path, web_root: Path | None = None, *, demo: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize_database(database_path)
        app.state.capture_latch = CaptureLatch()
        if demo:
            app.state.demo_response = seed_demo(database_path)
        scheduler = Scheduler(database_path, {}, on_storage_failure=app.state.capture_latch.pause)
        executor = PasswordExecutor()
        audit_housekeeping = AuditHousekeeping(scheduler.writer, on_failure=app.state.capture_latch.pause)
        try:
            await scheduler.start()
            await audit_housekeeping.start()
            app.state.owner_login = await OwnerLogin.create(scheduler.writer, executor)
            app.state.owner_bootstrap = OwnerBootstrap(scheduler.writer, executor)
        except BaseException:
            await audit_housekeeping.stop()
            await executor.close()
            await scheduler.stop()
            raise
        app.state.scheduler = scheduler
        app.state.audit_housekeeping = audit_housekeeping
        app.state.loop = asyncio.get_running_loop()
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            app.state.capture_latch.pause()
            await asyncio.to_thread(app.state.capture_latch.drain, 10)
            await audit_housekeeping.stop()
            await executor.close()
            await scheduler.stop()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.private_tls_dir = database_path.parent / "tls"
    app.include_router(auth_router)
    app.include_router(rotation_router)
    app.include_router(audit_router)
    app.include_router(mcp_auth_router)
    app.include_router(device_router)
    app.include_router(device_access_router)
    app.include_router(extension_router)
    app.include_router(privacy_router)
    app.include_router(preview_router)
    app.include_router(config_router)
    app.include_router(sources_router)
    app.include_router(private_settings_router)
    app.include_router(firewall_router)
    app.add_middleware(RejectWebSockets)

    app.middleware("http")(restrict_requests)

    @app.get("/healthz")
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/readyz", response_model=None)
    async def ready() -> ReadinessResponse | JSONResponse:
        if (not getattr(app.state, "ready", False) or app.state.scheduler.task.done()
                or app.state.audit_housekeeping.task.done()):
            return JSONResponse(ReadinessResponse(status="unavailable").model_dump(), status_code=503)
        return ReadinessResponse(status="ready")

    if demo:
        @app.get("/api/v1/demo")
        async def demo_data() -> DemoResponse:
            return DemoResponse.model_validate(app.state.demo_response)

    if web_root is not None:
        app.mount("/assets", StaticFiles(directory=web_root / "assets"), name="assets")

        async def index() -> FileResponse:
            return FileResponse(web_root / "index.html")

        ui_paths = (
            "/", "/overview", "/interests", "/timeline", "/knowledge", "/projects",
            "/projects/{project_id}", "/projects/{project_id}/resume", "/search", "/assistant",
            "/sources", "/settings/privacy", "/settings/resources", "/insights", "/recommendations",
            "/memory", "/goals", "/research", "/research/radar", "/pilot/summary",
        )
        for path in ui_paths:
            app.add_api_route(path, index, methods=["GET"], include_in_schema=False)

    return app
