#!/usr/bin/env python3.9
from __future__ import annotations

import logging
import os

import uvicorn
import uvloop

import app.config
import log

uvloop.install()


def main() -> int:
    if os.geteuid() == 0:
        log.warning("Running as root is not recommended!")

    uvicorn.run(
        "app.init_api:asgi_app",
        reload=app.config.DEBUG,
        log_level=logging.WARNING,
        server_header=False,
        date_header=False,
        host="127.0.0.1",
        port=app.config.SERVER_PORT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
