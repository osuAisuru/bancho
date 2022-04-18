from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.objects.channel import Channel
from app.objects.lists import ChannelList
from app.objects.lists import MatchList
from app.objects.lists import UserList

if TYPE_CHECKING:
    from app.objects.user import User

import app.usecases
import app.state
import log

users = UserList()
channels = ChannelList()
matches = MatchList()

bot: User


async def populate_sessions() -> None:
    app.state.sessions.bot = await app.usecases.user.fetch(id=1, db=True)
    if not app.state.sessions.bot:
        raise RuntimeError("Bot user not found")

    app.state.sessions.users.append(bot)
    log.debug(f"Bot user {app.state.sessions.bot} added to user list.")

    log.info("Fetching all channels from the database!")

    channel_collection = app.state.services.database.channels
    async for channel in channel_collection.find({}):
        channel.pop("_id")
        app.state.sessions.channels.append(Channel(**channel))

    app.state.sessions.channels.append(
        Channel(
            name="#lobby",
            topic="Lobby chat",
            auto_join=False,
        ),
    )

    app.state.sessions.channels.append(
        Channel(
            name="#announcements",
            topic="View announcements and first places!",
            auto_join=True,
        ),
    )
