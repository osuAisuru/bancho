from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional
from typing import TYPE_CHECKING
from typing import Union

import app.models
import app.packets
from app.constants.mode import Mode
from app.constants.privileges import BanchoPrivileges
from app.constants.privileges import Privileges
from app.constants.status import Status
from app.objects.channel import Channel

if TYPE_CHECKING:
    from app.objects.match import Match
    from app.state.services import Geolocation

from app.objects.stats import Stats
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
    blocked: list[int]

    channels: list[Channel]

    spectating: Optional[User]
    spectators: list[User]
    match: Optional[Match]

    stealth: bool
    in_lobby: bool
    friend_only_dms: bool

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

    def enqueue(self, data: Union[bytearray, bytes]) -> None:
        self.queue += data

    def dequeue(self) -> Optional[bytes]:
        if self.queue:
            data = bytes(self.queue)
            self.queue.clear()

            return data

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
