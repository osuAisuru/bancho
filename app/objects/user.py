from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import app.packets
import app.state
from app.constants.mode import Mode
from app.constants.privileges import BanchoPrivileges
from app.constants.privileges import Privileges
from app.constants.status import Status
from app.objects.channel import Channel
from app.objects.stats import Stats
from app.state.services import Geolocation
from app.typing import Message


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

    channels: list[Channel]

    spectating: Optional[int]
    spectators: list[int]

    def __repr__(self) -> str:
        return f"<{self.name} ({self.id})>"

    @property
    def current_stats(self) -> Stats:
        return self.stats[self.status.mode]

    @property
    def bancho_privileges(self) -> BanchoPrivileges:
        privileges = BanchoPrivileges(0)

        if not self.privileges & Privileges.DISALLOWED:
            privileges |= BanchoPrivileges.PLAYER

        if self.privileges & Privileges.SUPPORTER:
            privileges |= BanchoPrivileges.SUPPORTER

        if self.privileges & Privileges.ADMIN:
            privileges |= BanchoPrivileges.MODERATOR

        if self.privileges & Privileges.DEVELOPER:
            privileges |= BanchoPrivileges.DEVELOPER

        if self.privileges & Privileges.OWNER:
            privileges |= BanchoPrivileges.OWNER

        return privileges

    @property
    def remaining_silence(self) -> int:
        return max(0, int(self.silence_end - time.time()))

    @property
    def silenced(self) -> bool:
        return self.remaining_silence != 0

    @property
    def restricted(self) -> bool:
        return self.privileges & Privileges.DISALLOWED

    @property
    def banned(self) -> bool:
        return self.privileges & Privileges.BANNED

    def enqueue(self, data: bytes) -> None:
        self.queue += data

    def dequeue(self) -> Optional[bytes]:
        if self.queue:
            data = bytes(self.queue)
            self.queue.clear()

            return data

    async def set_privileges(self, privileges: Privileges) -> None:
        self.privileges = privileges

        user_collection = app.state.services.database.users
        await user_collection.update_one(
            {"id": self.id},
            {"$set": {"privileges": privileges}},
        )

    async def add_privilege(self, privilege: Privileges) -> None:
        await self.set_privileges(self.privileges | privilege)

    def receive_message(self, msg_content: str, sender: User) -> None:
        self.enqueue(
            app.packets.send_message(
                Message(
                    sender.name,
                    msg_content,
                    self.name,
                    sender.id,
                ),
            ),
        )

    async def update_activity(self) -> None:
        user_collection = app.state.services.database.users
        await user_collection.update_one(
            {"id": self.id},
            {"$set": {"latest_activity": int(time.time())}},
        )
