from __future__ import annotations

import asyncio
from typing import Any
from typing import TypedDict

import aioredis.client
import orjson

import app.packets
import app.state
import app.usecases
import app.utils
import log
from app.constants.mode import Mode
from app.constants.privileges import Privileges
from app.constants.status import Status
from app.typing import PubsubHandler


def register_pubsub(channel: str):
    def decorator(handler: PubsubHandler):
        app.state.PUBSUBS[channel] = handler

    return decorator


class StatusUpdate(TypedDict):
    id: int
    status: dict[str, Any]


@register_pubsub("user-status")
async def handle_status_update(payload: str) -> None:
    info: StatusUpdate = orjson.loads(payload)

    if not (user := app.usecases.user.cache_fetch(id=info["id"])):
        return

    user.status = Status.from_dict(info["status"])
    if not user.restricted:
        app.state.sessions.users.enqueue(app.packets.user_stats(user))


class ActivityUpdate(TypedDict):
    id: int
    activity: int


@register_pubsub("user-activity")
async def handle_latest_activity_update(payload: str) -> None:
    info: ActivityUpdate = orjson.loads(payload)

    if not (user := app.usecases.user.cache_fetch(id=info["id"])):
        return

    # this pubsub takes the assumption it was already updated in the database
    user.latest_activity = info["activity"]


class StatsUpdate(TypedDict):
    id: int
    mode: int


@register_pubsub("user-stats")
async def handle_user_stats_update(payload: str) -> None:
    info: StatsUpdate = orjson.loads(payload)

    if not (user := app.usecases.user.cache_fetch(id=info["id"])):
        return

    mode = Mode(info["mode"])
    new_stats = await app.usecases.stats.fetch(
        user_id=info["id"],
        country=user.geolocation.country.acronym,
        mode=mode,
    )

    user.stats[mode] = new_stats
    if not user.restricted:
        app.state.sessions.users.enqueue(app.packets.user_stats(user))


class PrivilegeUpdate(TypedDict):
    id: int
    privileges: int


@register_pubsub("user-privileges")
async def handle_privileges_change(payload: str) -> None:
    info: PrivilegeUpdate = orjson.loads(payload)

    if not (user := app.usecases.user.cache_fetch(id=info["id"])):
        return

    old_priv = user.privileges
    user.privileges = Privileges(info["privileges"])

    if old_priv & Privileges.RESTRICTED and not user.restricted:
        await app.usecases.user.handle_unrestriction(user)

    if not old_priv & Privileges.RESTRICTED and user.restricted:
        await app.usecases.user.handle_restriction(user)

    log.info(f"Updated privileges for user {user}")


class PublicMessage(TypedDict):
    channel: str
    message: str


@register_pubsub("send-public-message")
async def handle_public_message(payload: str) -> None:
    info: PublicMessage = orjson.loads(payload)

    if not (channel := app.state.sessions.channels.get_by_name(info["channel"])):
        return

    channel.send(info["message"], app.state.sessions.bot)


class PrivateMessage(TypedDict):
    recipient: int
    message: str


@register_pubsub("send-private-message")
async def handle_private_message(payload: str) -> None:
    info: PrivateMessage = orjson.loads(payload)

    if not (user := app.usecases.user.cache_fetch(id=info["recipient"])):
        return

    user.receive_message(
        info["message"],
        sender=app.state.sessions.bot,
    )


class RedisMessage(TypedDict):
    channel: bytes
    data: bytes


async def loop_pubsubs(pubsub: aioredis.client.PubSub) -> None:
    while True:
        try:
            message: RedisMessage = await pubsub.get_message(
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
    app.state.tasks.add(pubsub_loop)
