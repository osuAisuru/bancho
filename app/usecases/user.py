from __future__ import annotations

import copy
import time
from typing import Optional
from typing import Union
from uuid import uuid4

import app.packets
import app.state
import app.usecases
import app.utils
import log
from app.constants.mode import Mode
from app.constants.status import Status
from app.models import DBUser
from app.objects.user import User
from app.state.services import Country
from app.state.services import Geolocation
from app.typing import LoginData


async def create_session(
    login_data: LoginData,
    geolocation: Geolocation,
) -> Optional[User]:
    user_collection = app.state.services.database.users

    user = await user_collection.find_one(
        {"safe_name": app.utils.make_safe_name(login_data["username"])},
    )
    if not user:
        return None

    db_user = DBUser(**user)
    db_dict = db_user.__dict__
    db_dict.pop("country")

    stats = {}
    for mode in Mode:
        stats[mode] = await app.usecases.stats.fetch(
            db_user.id,
            geolocation.country.acronym,
            mode,
        )

    return User(
        **db_dict,
        geolocation=geolocation,
        osu_version=login_data["osu_version"],
        utc_offset=login_data["utc_offset"],
        status=Status.default(),
        login_time=int(time.time()),
        token=str(uuid4()),
        queue=bytearray(),
        stats=stats,
        channels=[],
        spectating=None,
        spectators=[],
        stealth=False,
        in_lobby=False,
    )


KWARGS_VALUES = Union[int, str]


def _parse_kwargs(
    kwargs: dict[str, KWARGS_VALUES],
) -> Optional[tuple[str, KWARGS_VALUES]]:
    for kwarg in ("id", "name", "token"):
        if val := kwargs.pop(kwarg, None):
            return (kwarg, val)

    return None


async def fetch(**kwargs) -> Optional[User]:
    if not (kwarg := _parse_kwargs(kwargs)):
        raise ValueError("incorrect kwargs passed to user.fetch()")

    key, val = kwarg
    for user in app.state.sessions.users:
        if getattr(user, key) == val:
            return user

    if kwargs.get("db"):
        user_collection = app.state.services.database.users
        user = await user_collection.find_one(
            {key: val},
        )
        if not user:
            return None

        db_user = DBUser(**user)
        db_dict = copy.copy(db_user.__dict__)
        db_dict.pop("country")

        return User(
            **db_dict,
            geolocation=Geolocation(country=Country.from_iso(db_user.country)),
            osu_version="",
            utc_offset=0,
            status=Status.default(),
            login_time=int(time.time()),
            token="",
            queue=bytearray(),
            stats={},  # TODO
            channels=[],
            spectating=None,
            spectators=[],
            stealth=False,
            in_lobby=False,
        )


def logout(user: User) -> None:
    user.token = ""

    if host := user.spectating:
        host.remove_spectator(user)

    for channel in user.channels:
        channel.remove_user(user)

    app.state.sessions.users.remove(user)

    if not user.restricted:
        app.state.sessions.users.enqueue(app.packets.logout(user.id))

    log.info(f"{user} logged out.")
