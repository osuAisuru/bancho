from __future__ import annotations

from enum import IntEnum
from typing import Optional
from typing import overload
from typing import TYPE_CHECKING
from typing import Union

import app.config
from app.constants.mode import Mode
from app.constants.mods import Mods

if TYPE_CHECKING:
    from app.objects.user import User
    from app.objects.channel import Channel


class SlotStatus(IntEnum):
    OPEN = 1
    LOCKED = 2
    NOT_READY = 4
    READY = 8
    NO_MAP = 16
    PLAYING = 32
    COMPLETE = 64
    QUIT = 128

    HAS_USER = NOT_READY | READY | NO_MAP | PLAYING | COMPLETE


class MatchTeams(IntEnum):
    NEUTRAL = 0
    BLUE = 1
    RED = 2


class MatchWinConditions(IntEnum):
    SCORE = 0
    ACCURACY = 1
    COMBO = 2
    SCOREV2 = 3


class MatchTeamTypes(IntEnum):
    HEAD_TO_HEAD = 0
    TAG_COOP = 1
    TEAM_VS = 2
    TAG_TEAM_VS = 3


class Slot:
    def __init__(self) -> None:
        self.user: Optional[User] = None
        self.status = SlotStatus.OPEN
        self.team = MatchTeams.NEUTRAL
        self.mods = Mods.NOMOD
        self.loaded = False
        self.skipped = False

    def empty(self) -> bool:
        return self.user is None

    def copy_from(self, other: Slot) -> None:
        self.user = other.user
        self.status = other.status
        self.team = other.team
        self.mods = other.mods

    def reset(self, new_status: SlotStatus = SlotStatus.OPEN) -> None:
        self.user = None
        self.status = new_status
        self.team = MatchTeams.NEUTRAL
        self.mods = Mods.NOMOD
        self.loaded = False
        self.skipped = False


class Match:
    def __init__(self) -> None:
        self.id = 0
        self.name = ""
        self.password = ""

        self.host_id = 0
        self._refs: set[User] = set()

        self.map_id = 0
        self.map_md5 = ""
        self.map_name = ""
        self.last_map_id = 0

        self.mods = Mods.NOMOD
        self.mode = Mode.STD
        self.freemod = False

        self.chat: Optional[Channel] = None
        self.slots = [Slot() for _ in range(16)]  # osu can handle up to 16 users

        self.team_type = MatchTeamTypes.HEAD_TO_HEAD
        self.win_condition = MatchWinConditions.SCORE

        self.in_progress = False
        self.seed = 0  # mania

        self.tourney_clients: set[int] = set()

    @property
    def url(self) -> str:
        return f"osump://{self.id}/{self.password}"

    @property
    def embed(self) -> str:
        return f"[{self.url} {self.name}]"

    @property
    def map_url(self):
        return f"https://osu.{app.config.SERVER_DOMAIN}/beatmaps/{self.map_id}"

    @property
    def map_embed(self) -> str:
        return f"[{self.map_url} {self.map_name}]"

    def __contains__(self, user: User) -> bool:
        return user in {slot.user for slot in self.slots}

    def __repr__(self) -> str:
        return f"<{self.name} ({self.id})>"

    @overload
    def __getitem__(self, index: int) -> Slot:
        ...

    @overload
    def __getitem__(self, index: slice) -> list[Slot]:
        ...

    def __getitem__(self, index: Union[int, slice]) -> Union[Slot, list[Slot]]:
        return self.slots[index]

    def get_slot(self, user: User) -> Optional[Slot]:
        for slot in self.slots:
            if user is slot.user:
                return slot

    def get_slot_id(self, user: User) -> Optional[int]:
        for idx, slot in enumerate(self.slots):
            if user is slot.user:
                return idx

    def get_free(self) -> Optional[int]:
        for idx, slot in enumerate(self.slots):
            if slot.status == SlotStatus.OPEN:
                return idx

    def copy(self, other: Match) -> None:
        self.map_id = other.map_id
        self.map_md5 = other.map_md5
        self.map_name = other.map_name
        self.freemod = other.freemod
        self.mode = other.mode
        self.team_type = other.team_type
        self.win_condition = other.win_condition
        self.mods = other.mods
        self.name = other.name

    def unready_users(self, expected: SlotStatus = SlotStatus.READY) -> None:
        for slot in self.slots:
            if slot.status == expected:
                slot.status = SlotStatus.NOT_READY
