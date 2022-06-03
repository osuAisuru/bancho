from __future__ import annotations

from datetime import datetime
from typing import Optional

import orjson

import app.state
import app.usecases
from app.constants.privileges import Privileges
from app.objects.beatmap import RankedStatus
from app.objects.user import User


def register_command(
    name: str,
    aliases: list[str] = None,
    privileges: Privileges = Privileges.VERIFIED,
):
    def decorator(handler):
        app.state.commands[name] = {
            "callback": handler,
            "privileges": privileges,
        }

        if aliases:
            for alias in aliases:
                app.state.commands[alias] = {
                    "callback": handler,
                    "privileges": privileges,
                }

    return decorator


@register_command("!map", aliases=["!m"], privileges=Privileges.NOMINATOR)
async def rank_command(user: User, args: list[str]) -> str:
    if not (bmap := user.last_np):
        return "You must /np a map first!"

    if len(args) < 1:
        return "You must provide a new status!"

    new_status_type = args[0]
    set_or_map = args[1] if len(args) > 1 else None
    if set_or_map not in ("set", "map"):
        return "Invalid rank type! (set/map)"

    new_status = RankedStatus.from_str(new_status_type)
    if new_status is None:
        return "Invalid status! (rank/unrank/love/unlove)"

    rank_type = "set" if not set_or_map else set_or_map

    if rank_type == "map":
        maps = [bmap]
    else:
        maps = await app.usecases.beatmap.fetch_by_set_id(bmap.set_id)

    if not maps:
        return "Couldn't find map!"

    for _map in maps:
        _map.status = new_status
        _map.frozen = True

        await app.state.services.redis.publish(
            "map-status",
            orjson.dumps(
                {
                    "md5": _map.md5,
                    "new_status": int(new_status),
                },
            ),
        )

    return "Map/set updated!"


@register_command("!restrict", privileges=Privileges.ADMIN)
async def restrict_command(user: User, args: list[str]) -> str:
    if len(args) < 2:
        return "You must provide a user and a reason!"

    username = args[0]
    reason = " ".join(args[1:])

    target = await app.usecases.user.fetch(name=username, db=True)
    if not target:
        return f"Couldn't find user {username}!"

    if target.restricted:
        return f"{target} is already restricted!"

    await app.usecases.user.restrict(target, reason, sender=user)
    return f"{target} has been restricted for {reason}!"


@register_command("!unrestrict", privileges=Privileges.ADMIN)
async def unrestrict_command(user: User, args: list[str]) -> str:
    if len(args) < 2:
        return "You must provide a user and a reason!"

    username = args[0]
    reason = " ".join(args[1:])

    target = await app.usecases.user.fetch(name=username, db=True)
    if not target:
        return f"Couldn't find user {username}!"

    if not target.restricted:
        return f"{target} is already unrestricted!"

    await app.usecases.user.unrestrict(target, reason, sender=user)
    return f"{target} has been unrestricted for {reason}!"


@register_command("!freeze", privileges=Privileges.ADMIN)
async def freeze_command(user: User, args: list[str]) -> str:
    if len(args) < 2:
        return "You must provide a user and a reason!"

    username = args[0]
    reason = " ".join(args[1:])

    target = await app.usecases.user.fetch(name=username, db=True)
    if not target:
        return f"Couldn't find user {username}!"

    if target.frozen:
        pretty_time = datetime.fromtimestamp(target.freeze_timer).strftime(
            "%Y-%m-%d %H:%M:%S",
        )
        return f"{target} is already frozen! Their timer expires at {pretty_time}."

    await app.usecases.user.freeze(target, reason, sender=user)
    return f"{target} has been frozen for {reason}!"


@register_command("!unfreeze", privileges=Privileges.ADMIN)
async def unfreeze_command(user: User, args: list[str]) -> str:
    if len(args) < 2:
        return "You must provide a user and a reason!"

    username = args[0]
    reason = " ".join(args[1:])

    target = await app.usecases.user.fetch(name=username, db=True)
    if not target:
        return f"Couldn't find user {username}!"

    if not target.frozen:
        return f"{target} is not frozen!"

    await app.usecases.user.unfreeze(target, reason, sender=user)
    return f"{target} has been unfrozen for {reason}!"


async def handle_command(user: User, message: str) -> str:
    message_split = message.split(" ")

    cmd = message_split[0]
    args = message_split[1:]

    if handler := app.state.commands.get(cmd):
        if user.privileges & handler["privileges"]:
            return await handler["callback"](user, args)

    return "Command not found!"
