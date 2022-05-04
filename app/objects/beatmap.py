from __future__ import annotations

import functools
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Any
from typing import Optional

import app.config
from app.constants.mode import Mode


class RankedStatus(IntEnum):
    NOT_SUBMITTED = -1
    PENDING = 0
    UPDATE_AVAILABLE = 1
    RANKED = 2
    APPROVED = 3
    QUALIFIED = 4
    LOVED = 5

    @functools.cached_property
    def osu_api(self) -> int:
        return {
            self.PENDING: 0,
            self.RANKED: 1,
            self.APPROVED: 2,
            self.QUALIFIED: 3,
            self.LOVED: 4,
        }.get(self)

    @classmethod
    @functools.cache
    def from_osu_api(cls, osu_api_status: int) -> RankedStatus:
        return {
            -2: cls.PENDING,  # graveyard
            -1: cls.PENDING,  # wip
            0: cls.PENDING,
            1: cls.RANKED,
            2: cls.APPROVED,
            3: cls.QUALIFIED,
            4: cls.LOVED,
        }.get(osu_api_status, cls.UPDATE_AVAILABLE)

    @classmethod
    @functools.cache
    def from_direct(cls, direct_status: int) -> RankedStatus:
        return {
            0: cls.RANKED,
            2: cls.PENDING,
            3: cls.QUALIFIED,
            5: cls.PENDING,  # graveyard
            7: cls.RANKED,  # played before
            8: cls.LOVED,
        }.get(direct_status, cls.UPDATE_AVAILABLE)

    @classmethod
    def from_str(cls, status_str: str) -> Optional[RankedStatus]:
        return {
            "rank": cls.RANKED,
            "unrank": cls.PENDING,
            "love": cls.LOVED,
            "unlove": cls.PENDING,
        }.get(status_str, None)


DEFAULT_LAST_UPDATE = datetime(1970, 1, 1)


@dataclass
class Beatmap:
    md5: str
    id: int
    set_id: int

    artist: str
    title: str
    version: str
    creator: str

    total_length: int

    status: RankedStatus

    plays: int
    passes: int
    mode: Mode

    cs: float
    od: float
    ar: float
    hp: float
    diff: float

    last_update: datetime = DEFAULT_LAST_UPDATE

    max_combo: int = 0
    bpm: float = 0.0
    filename: str = ""
    frozen: bool = False
    rating: Optional[float] = None

    @property
    def full_name(self) -> str:
        return f"{self.artist} - {self.title} [{self.version}]"

    @property
    def url(self) -> str:
        return f"https://osu.{app.config.SERVER_DOMAIN}/beatmaps/{self.id}"

    @property
    def set_url(self) -> str:
        return f"https://osu.{app.config.SERVER_DOMAIN}/beatmapsets/{self.set_id}"

    @property
    def embed(self) -> str:
        return f"[{self.url} {self.full_name}]"

    @property
    def gives_pp(self) -> bool:
        return self.status in (RankedStatus.RANKED, RankedStatus.APPROVED)

    @property
    def has_leaderboard(self) -> bool:
        return self.status >= RankedStatus.RANKED

    def osu_string(self, score_count: int, rating: float) -> str:
        return (
            f"{int(self.status)}|false|{self.id}|{self.set_id}|{score_count}|0|\n"  # |0| = featured artist bs
            f"0\n{self.full_name}\n{rating:.1f}"  # 0 = offset
        )

    def dict(self) -> dict[str, Any]:
        return {
            "md5": self.md5,
            "id": self.id,
            "set_id": self.set_id,
            "artist": self.artist,
            "title": self.title,
            "version": self.version,
            "creator": self.creator,
            "total_length": self.total_length,
            "status": self.status.value,
            "plays": self.plays,
            "passes": self.passes,
            "mode": self.mode.value,
            "cs": self.cs,
            "od": self.od,
            "ar": self.ar,
            "hp": self.hp,
            "diff": self.diff,
            "last_update": self.last_update.isoformat(),
            "max_combo": self.max_combo,
            "bpm": self.bpm,
            "filename": self.filename,
            "frozen": self.frozen,
        }
