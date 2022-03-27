from __future__ import annotations

import pprint

from fastapi import FastAPI
from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import ORJSONResponse
from fastapi.responses import Response
from starlette.middleware.base import RequestResponseEndpoint

import app.config
import app.state
import log


def init_events(asgi_app: FastAPI) -> None:
    @asgi_app.on_event("startup")
    async def on_startup() -> None:
        await app.state.services.redis.initialize()

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

    import app.bancho

    for subdomain in ("c", "c4", "ce"):
        asgi_app.host(f"{subdomain}.{app.config.SERVER_DOMAIN}", app.bancho.router)


asgi_app = init_bancho()
