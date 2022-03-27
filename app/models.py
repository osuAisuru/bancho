from __future__ import annotations

from pydantic import BaseModel

from app.constants.privileges import Privileges


class DBUser(BaseModel):
    id: int
    name: str
    safe_name: str

    password_bcrypt: str
    register_time: int
    latest_activity: int
    email: str

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
