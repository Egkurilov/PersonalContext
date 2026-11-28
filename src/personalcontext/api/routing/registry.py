"""Register the application's explicit HTTP route sets."""

from fastapi import FastAPI

from personalcontext.audit.http_routes import router as audit_router
from personalcontext.auth.http_routes import router as auth_router
from personalcontext.auth.rotation_http import router as rotation_router
from personalcontext.devices.device_http import router as device_access_router
from personalcontext.devices.extension_http import router as extension_router
from personalcontext.devices.http_routes import router as device_router
from personalcontext.mcp_auth.http import router as mcp_auth_router
from personalcontext.network.firewall.http import router as firewall_router
from personalcontext.network.listener.http import router as listener_router
from personalcontext.network.settings_http import router as private_settings_router
from personalcontext.privacy.http_routes import router as privacy_router
from personalcontext.privacy.preview_routes import router as preview_router
from personalcontext.sources.config_http import router as config_router
from personalcontext.sources.http_routes import router as sources_router


def register_routes(app: FastAPI) -> None:
    for router in (auth_router, rotation_router, audit_router, mcp_auth_router, device_router, device_access_router,
                   extension_router, privacy_router, preview_router, config_router, sources_router,
                   private_settings_router, firewall_router, listener_router):
        app.include_router(router)
