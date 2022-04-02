from __future__ import annotations

from pydantic import BaseModel

from app.constants.action import Action
from app.constants.privileges import Privileges
from app.typing import i32
from app.typing import Message
from app.typing import String
from app.typing import u32
from app.typing import u8


class DBUser(BaseModel):
    id: int
    name: str
    safe_name: str

    password_bcrypt: str
    register_time: int
    latest_activity: int
    email: str
    country: str

    privileges: Privileges
    silence_end: int

    friends: list[int]


class DBStats(BaseModel):
    total_score: int
    ranked_score: int

    accuracy: float
    pp: int

    max_combo: int
    total_hits: int

    playcount: int
    playtime: int


class ChangeActionStructure:
    action: u8
    info_text: String
    map_md5: String
    mods: u32
    mode: u8
    map_id: i32


class SendMessageStructure:
    message: Message


class StartSpectatingStructure:
    target_id: i32
