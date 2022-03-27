from __future__ import annotations

import time
from typing import Optional
from uuid import uuid4

import app.usecases
import app.utils
from app.constants.mode import Mode
from app.constants.status import Status
from app.models import DBUser
from app.objects.user import User
from app.state.services import database
from app.state.services import Geolocation
from app.typing import LoginData


async def create(login_data: LoginData, geolocation: Geolocation) -> Optional[User]:
    user = database.find_one(
        {"safe_name": app.utils.make_safe_name(login_data["username"])},
    )
    if not user:
        return None

    db_user = DBUser(**user)

    stats = {}
    for mode in Mode:
        stats[mode] = await app.usecases.stats.fetch(
            db_user.id,
            geolocation.country.acronym,
            mode,
        )

    return User(
        **db_user.dict(),
        geolocation=geolocation,
        osu_version=login_data["osu_version"],
        utc_offset=login_data["utc_offset"],
        status=Status.default(),
        login_time=int(time.time()),
        token=str(uuid4()),
        queue=bytearray(),
        stats=stats,
        spectating=None,
        spectators=[],
    )


async def fetch(**kwargs) -> Optional[User]:
    ...
