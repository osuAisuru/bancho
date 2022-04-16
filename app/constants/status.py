from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.constants.action import Action
from app.constants.mode import Mode
from app.constants.mods import Mods


@dataclass
class Status:
    action: Action
    info_text: str
    map_md5: str
    mods: Mods
    mode: Mode
    map_id: int

    @classmethod
    def default(cls) -> Status:
        return Status(
            Action.IDLE,
            "",
            "",
            Mods.NOMOD,
            Mode.STD,
            0,
        )

    @classmethod
    def from_dict(cls, status: dict[str, Any]) -> Status:
        return Status(
            Action(status["action"]),
            status["info_text"],
            status["map_md5"],
            Mods(status["mods"]),
            Mode(status["mode"]),
            status["map_id"],
        )
