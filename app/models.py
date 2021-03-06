from __future__ import annotations

from pydantic import BaseModel

from app.constants.privileges import Privileges
from app.typing import i32
from app.typing import i32_list
from app.typing import Message
from app.typing import OsuMatch
from app.typing import ReplayFrameBundle
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
    blocked: list[int]


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


class SpectateFramesStructure:
    frame_bundle: ReplayFrameBundle


class ChannelStructure:
    channel_name: String


class FriendStructure:
    target_id: i32


class StatsRequestStructure:
    user_ids: i32_list


class UserPresenceRequestStructure:
    user_ids: i32_list


class ToggleDMStructure:
    value: i32


class MatchStructure:
    match: OsuMatch


class JoinMatchStructure:
    match_id: i32
    match_password: String


class MatchSlotStructure:
    slot_id: i32


class RawStructure:
    data: bytearray


class MatchModsStructure:
    mods: i32


class MatchIDSStructure:
    match_id: i32


class MatchInviteStructure:
    user_id: i32
