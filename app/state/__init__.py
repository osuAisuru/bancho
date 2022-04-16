from __future__ import annotations

from . import cache
from . import services
from . import sessions
from app.typing import PacketHandler
from app.typing import PubsubHandler

PACKETS: dict[int, PacketHandler] = {}
RESTRICTED_PACKETS: dict[int, PacketHandler] = {}

PUBSUBS: dict[str, PubsubHandler] = {}
