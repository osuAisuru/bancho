from __future__ import annotations

import asyncio

import aioredis.client
import orjson

import app.packets
import app.state
import app.usecases
import app.utils
import log
from app.constants.status import Status
from app.typing import PubsubHandler


def register_pubsub(channel: str):
    def decorator(handler: PubsubHandler):
        app.state.PUBSUBS[channel] = handler

    return decorator


@register_pubsub("user-status")
async def handle_status_update(payload: str) -> None:
    info = orjson.loads(payload)

    if not (user := app.usecases.user.cache_fetch(id=info["id"])):
        return

    user.status = Status.from_dict(info["status"])
    if not user.restricted:
        app.state.sessions.users.enqueue(app.packets.user_stats(user))

    log.info(f"Updated {user}'s status from Redis")


async def loop_pubsubs(pubsub: aioredis.client.PubSub) -> None:
    while True:
        try:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message is not None:
                if handler := app.state.PUBSUBS.get(message["channel"].decode()):
                    await handler(message["data"].decode())

            await asyncio.sleep(0.01)
        except asyncio.TimeoutError:
            pass


async def initialise_pubsubs() -> None:
    pubsub = app.state.services.redis.pubsub()
    await pubsub.subscribe(*[channel for channel in app.state.PUBSUBS.keys()])

    pubsub_loop = asyncio.create_task(loop_pubsubs(pubsub))
    app.state.sessions.tasks.add(pubsub_loop)
