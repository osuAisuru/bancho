from __future__ import annotations

import time
from typing import Literal
from typing import Optional
from typing import TypedDict

from fastapi import APIRouter
from fastapi import Request
from fastapi.param_functions import Header
from fastapi.responses import HTMLResponse
from fastapi.responses import Response

import app.usecases
from app.state.services import Geolocation
from app.typing import LoginData

router = APIRouter(tags=["Bancho API"])


@router.get("/")
async def index_html() -> HTMLResponse:
    return HTMLResponse("and why are you here?")


class LoginResponse(TypedDict):
    token: str
    body: bytearray


def parse_login_data(data: bytes) -> LoginData:
    (
        username,
        password_md5,
        remainder,
    ) = data.decode().split("\n", maxsplit=2)

    (
        osu_version,
        utc_offset,
        display_city,
        client_hashes,
        pm_private,
    ) = remainder.split("|", maxsplit=4)

    (
        osu_path_md5,
        adapters_str,
        adapters_md5,
        uninstall_md5,
        disk_signature_md5,
    ) = client_hashes[:-1].split(":", maxsplit=4)

    return {
        "username": username,
        "password_md5": password_md5.encode(),
        "osu_version": osu_version,
        "utc_offset": int(utc_offset),
        "display_city": display_city == "1",
        "pm_private": pm_private == "1",
        "osu_path_md5": osu_path_md5,
        "adapters_str": adapters_str,
        "adapters_md5": adapters_md5,
        "uninstall_md5": uninstall_md5,
        "disk_signature_md5": disk_signature_md5,
    }


@router.post("/")
async def bancho_handler(
    request: Request,
    osu_token: Optional[str] = Header(None),
    user_agent: Literal["osu!"] = Header(...),
) -> Response:
    geoloc = Geolocation.from_ip(request.headers)
    body = await request.body()

    if not osu_token:
        login_data = await login(body, geoloc)

        return Response(
            content=bytes(login_data["body"]),
            headers={"cho-token": login_data["token"]},
        )

    # user already logged in
    return Response(b"")


async def login(
    body: bytes,
    geoloc: Geolocation,
) -> LoginData:
    start = time.perf_counter_ns()

    login_data = parse_login_data(body)

    if await app.usecases.user.fetch(name=login_data["username"]):
        ...  # already logged in

    user = await app.usecases.user.create(login_data, geoloc)
    if not user:
        ...  # auth failed

    if not app.usecases.password.verify_password(
        login_data["password_md5"],
        user.password_bcrypt,
    ):
        ...  # invalid password
