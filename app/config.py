from __future__ import annotations

from starlette.config import Config
from starlette.datastructures import Secret

cfg = Config(".env")

MONGODB_DSN: Secret = cfg("MONGODB_DSN", cast=Secret)
REDIS_DSN: Secret = cfg("REDIS_DSN", cast=Secret)

SERVER_DOMAIN: str = cfg("SERVER_DOMAIN")
SERVER_PORT: int = cfg("SERVER_PORT", cast=int)

DEBUG: bool = cfg("DEBUG", cast=bool)

# do NOT change
VERSION = "0.1.0"
