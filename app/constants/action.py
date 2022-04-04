from __future__ import annotations

from enum import IntEnum


class Action(IntEnum):
    IDLE = 0
    AFK = 1
    PLAYING = 2
    EDITING = 3
    MODDING = 4
    MULTIPLAYER = 5
    WATCHING = 6
    UNKNOWN = 7
    TESTING = 8
    SUBMITTING = 9
    PAUSED = 10
    LOBBY = 11
    MULTIPLAYING = 12
    OSUDIRECT = 13


class ReplayAction(IntEnum):
    STANDARD = 0
    NEW_SONG = 1
    SKIP = 2
    COMPLETION = 3
    FAIL = 4
    PAUSE = 5
    UNPAUSE = 6
    SONG_SELECT = 7
    WATCHING_OTHER = 8
