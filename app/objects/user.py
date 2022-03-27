from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.constants.mode import Mode
from app.constants.privileges import Privileges
from app.constants.status import Status
from app.objects.stats import Stats
from app.state.services import Geolocation


@dataclass
class User:
    id: int
    name: str
    safe_name: str

    password_bcrypt: str
    register_time: int
    latest_activity: int
    email: str

    privileges: Privileges
    silence_end: int

    geolocation: Geolocation
    utc_offset: int
    osu_version: str
    status: Status
    login_time: int

    token: str
    queue: bytearray

    stats: dict[Mode, Stats]
    friends: list[int]

    spectating: Optional[int]
    spectators: list[int]

    @property
    def current_stats(self) -> Stats:
        return self.stats[self.status.mode]
