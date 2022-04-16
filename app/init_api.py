from __future__ import annotations

import pprint

from fastapi import FastAPI
from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import ORJSONResponse
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.base import RequestResponseEndpoint

import app.config
import app.state
import app.usecases
import log


def init_events(asgi_app: FastAPI) -> None:
    @asgi_app.on_event("startup")
    async def on_startup() -> None:
        app.state.services.client = AsyncIOMotorClient(str(app.config.MONGODB_DSN))
        app.state.services.database = app.state.services.client.aisuru

        await app.state.services.redis.initialize()
        await app.state.sessions.populate_sessions()

        log.info("Bancho is running!")

    @asgi_app.on_event("shutdown")
    async def on_shutdown() -> None:
        await app.state.services.redis.close()

        log.info("Bancho has stopped!")

    @asgi_app.middleware("http")
    async def http_middleware(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        try:
            return await call_next(request)
        except RuntimeError as err:
            if err.args[0] == "No response returned.":
                return Response("skill issue")

            raise err

    @asgi_app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        e: RequestValidationError,
    ) -> Response:
        log.warning(f"Validation error:\n{pprint.pformat(e.errors())}")

        return ORJSONResponse(
            content=jsonable_encoder(e.errors()),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


def init_bancho() -> FastAPI:
    asgi_app = FastAPI()

    init_events(asgi_app)

    import app.api.bancho
    import app.api.api

    for subdomain in ("c", "c4", "ce"):
        asgi_app.host(f"{subdomain}.{app.config.SERVER_DOMAIN}", app.api.bancho.router)

    asgi_app.host(f"cho_api.{app.config.SERVER_DOMAIN}", app.api.api.router)

    return asgi_app


asgi_app = init_bancho()
