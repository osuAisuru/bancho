from __future__ import annotations

from typing import Optional

import app.state
from app.objects.channel import Channel


async def fetch(channel_name: str) -> Optional[Channel]:
    channel_collection = app.state.services.database.channels

    channel = await channel_collection.find_one({"name": channel_name})
    if not channel:
        return

    channel.pop("_id")
    return Channel(**channel)
