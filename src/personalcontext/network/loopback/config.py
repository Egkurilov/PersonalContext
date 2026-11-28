"""Construct the local server without request-target access logs."""

import uvicorn
from fastapi import FastAPI


def loopback_server_config(app: FastAPI) -> uvicorn.Config:
    return uvicorn.Config(app, host="127.0.0.1", port=17890, workers=1,
                          log_level="warning", proxy_headers=False, access_log=False, ws="none")
