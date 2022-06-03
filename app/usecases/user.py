from __future__ import annotations

import copy
import time
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import Optional
from typing import Union
from uuid import uuid4

import orjson

import app.models
import app.packets
import app.state
import app.usecases
import app.utils
import log
from app.constants.action import Action
from app.constants.mode import Mode
from app.constants.mods import Mods
from app.constants.privileges import Privileges
from app.constants.status import Status
from app.models import DBUser
from app.objects.channel import Channel
from app.objects.match import Match
from app.objects.match import MatchTeams
from app.objects.match import MatchTeamTypes
from app.objects.match import Slot
from app.objects.match import SlotStatus
from app.objects.user import ClientInfo
from app.objects.user import User
from app.state.services import Country
from app.state.services import Geolocation
from app.typing import LoginData


async def create_session(
    login_data: LoginData,
    geolocation: Geolocation,
    client_info: Optional[ClientInfo] = None,
) -> Optional[User]:
    user_collection = app.state.services.database.users

    user = await user_collection.find_one(
        {"safe_name": app.utils.make_safe_name(login_data["username"])},
    )
    if not user:
        return None

    db_user = DBUser(**user)
    db_dict = db_user.__dict__

    db_country = db_dict.pop("country")
    if not db_country or db_country == "xx":
        await user_collection.update_one(
            {"id": db_user.id},
            {"$set": {"country": geolocation.country.acronym}},
        )

    stats = {}
    for mode in Mode:
        stats[mode] = await app.usecases.stats.fetch(
            db_user.id,
            geolocation.country.acronym,
            mode,
        )

    return User(  # TODO: convert user to dataclass to simplify this
        **db_dict,
        password_md5=login_data["password_md5"].decode(),
        geolocation=geolocation,
        utc_offset=login_data["utc_offset"],
        status=Status.default(),
        login_time=int(time.time()),
        token=str(uuid4()),
        queue=bytearray(),
        stats=stats,
        channels=[],
        spectating=None,
        spectators=[],
        stealth=False,
        in_lobby=False,
        tourney=False,
        friend_only_dms=login_data["pm_private"],
        match=False,
        client_info=client_info,
    )


KWARGS_VALUES = Union[int, str]


def _parse_kwargs(
    kwargs: dict[str, KWARGS_VALUES],
) -> Optional[tuple[str, KWARGS_VALUES]]:
    for kwarg in ("id", "name", "token"):
        if val := kwargs.pop(kwarg, None):
            return (kwarg, val)

    return None


def cache_fetch(**kwargs) -> Optional[User]:
    if not (kwarg := _parse_kwargs(kwargs)):
        raise ValueError("incorrect kwargs passed to user.cache_fetch()")

    key, val = kwarg
    for user in app.state.sessions.users:
        if getattr(user, key) == val:
            return user


async def fetch(**kwargs) -> Optional[User]:
    if user := cache_fetch(**kwargs):
        return user

    if kwargs.get("db"):
        if not (kwarg := _parse_kwargs(kwargs)):
            raise ValueError("incorrect kwargs passed to user.fetch()")

        key, val = kwarg

        user_collection = app.state.services.database.users
        user = await user_collection.find_one(
            {key: val},
        )
        if not user:
            return None

        db_user = DBUser(**user)
        db_dict = copy.copy(db_user.__dict__)
        db_dict.pop("country")

        return User(  # TODO: convert user to dataclass to simplify this
            **db_dict,
            password_md5=None,
            geolocation=Geolocation(country=Country.from_iso(db_user.country)),
            utc_offset=0,
            status=Status.default(),
            login_time=int(time.time()),
            token="",
            queue=bytearray(),
            stats={},  # TODO
            channels=[],
            spectating=None,
            spectators=[],
            stealth=False,
            in_lobby=False,
            friend_only_dms=False,
            tourney=False,
            match=False,
            client_info=None,
        )


async def save_login(user: User) -> None:
    login_collection = app.state.services.database.logins
    await login_collection.insert_one(
        {
            "userid": user.id,
            "ip": user.geolocation.ip,
            "osu_ver": user.client_info.client.date_str,
            "osu_stream": user.client_info.client.stream,
            "datetime": datetime.now().isoformat(),
        },
    )

    hashes_collection = app.state.services.database.client_hashes
    await hashes_collection.update_one(
        {
            "userid": user.id,
            "osu_md5": user.client_info.osu_md5,
            "adapters": user.client_info.adapters_md5,
            "uninstall": user.client_info.uninstall_md5,
            "disk": user.client_info.disk_md5,
        },
        {
            "$inc": {"occurrences": 1},
            "$set": {"latest_time": datetime.now().isoformat()},
            "$setOnInsert": {
                "userid": user.id,
                "osu_md5": user.client_info.osu_md5,
                "adapters": user.client_info.adapters_md5,
                "uninstall": user.client_info.uninstall_md5,
                "disk": user.client_info.disk_md5,
            },
        },
        upsert=True,
    )


async def find_hardware_matches(user: User) -> Optional[list[int]]:
    hw_checks = {"userid": {"$ne": user.id}}
    if user.client_info.running_under_wine:
        hw_checks["uninstall"] = user.client_info.adapters_md5
    else:
        hw_checks |= {
            "adapters": user.client_info.adapters_md5,
            "uninstall": user.client_info.uninstall_md5,
            "disk": user.client_info.disk_md5,
        }

    hashes_collection = app.state.services.database.client_hashes
    hw_matches = await hashes_collection.find(hw_checks).to_list(length=None)

    if hw_matches:
        return hw_matches

    return None


def logout(user: User) -> None:
    user.token = ""

    if host := user.spectating:
        remove_spectator(host, user)

    for channel in user.channels:
        channel.remove_user(user)

    app.state.sessions.users.remove(user)

    if not user.restricted:
        app.state.sessions.users.enqueue(app.packets.logout(user.id))

    log.info(f"{user} logged out.")


def join_match(user: User, match: Match, password: str) -> bool:
    if user.match:
        log.warning(
            f"{user} tried to join multi {match} while being in {user.match} already",
        )
        user.enqueue(app.packets.match_join_fail())
        return False

    if user.id in match.tourney_clients:
        user.enqueue(app.packets.match_join_fail())
        return False

    if user is not app.usecases.match.host(match):
        if password != match.password and user not in app.state.sessions.users.staff:
            log.warning(f"{user} tried to join {match} with incorrect password")
            user.enqueue(app.packets.match_join_fail())
            return False

        if (slot_id := match.get_free()) is None:
            log.warning(f"{user} tried to join full match {match}")
            user.enqueue(app.packets.match_join_fail())
            return False
    else:
        slot_id = 0

    if not join_channel(user, match.chat):
        log.warning(f"{user} failed to join multi channel {match.chat}")
        return False

    if (lobby := app.state.sessions.channels["#lobby"]) in user.channels:
        leave_channel(user, lobby)

    slot: Slot = match.slots[0 if slot_id == -1 else slot_id]

    if match.team_type in (MatchTeamTypes.TEAM_VS, MatchTeamTypes.TAG_TEAM_VS):
        slot.team = MatchTeams.RED

    slot.status = SlotStatus.NOT_READY
    slot.user = user

    user.match = match
    user.enqueue(app.packets.match_join_success(match))
    app.usecases.match.enqueue_state(match)

    return True


def leave_match(user: User) -> None:
    if not user.match:
        log.warning(f"{user} tried to leave multi without being in one")
        return

    slot = user.match.get_slot(user)
    assert slot is not None

    if slot.status == SlotStatus.LOCKED:
        new_status = SlotStatus.LOCKED
    else:
        new_status = SlotStatus.OPEN

    slot.reset(new_status=new_status)

    leave_channel(user, user.match.chat)

    if all(slot.empty() for slot in user.match.slots):
        log.info(f"Match {user.match} is empty, deleting")

        app.state.sessions.matches.remove(user.match)
        if lobby := app.state.sessions.channels["#lobby"]:
            lobby.enqueue(app.packets.dispose_match(user.match.id))
    else:
        if user is app.usecases.match.host(user.match):
            for slot in user.match.slots:
                if slot.status & SlotStatus.HAS_USER:
                    user.match.host_id = slot.user.id
                    app.usecases.match.host(user.match).enqueue(
                        app.packets.match_transfer_host(),
                    )
                    break

        if user in user.match._refs:
            user.match._refs.remove(user)

        app.usecases.match.enqueue_state(user.match)

    user.match = None


async def set_privileges(user: User, privileges: Privileges) -> None:
    user.privileges = privileges

    user_collection = app.state.services.database.users
    await user_collection.update_one(
        {"id": user.id},
        {"$set": {"privileges": privileges.value}},
    )

    await app.state.services.redis.publish(
        "user-privileges",
        orjson.dumps({"id": user.id, "privileges": privileges.value}),
    )


async def add_privilege(user: User, privilege: Privileges) -> None:
    await set_privileges(user, user.privileges | privilege)


def join_channel(user: User, channel: Channel) -> bool:
    if (
        user in channel
        or not channel.has_permission(user.privileges)
        or channel.name == "#lobby"
        and not user.in_lobby
    ):
        return False

    channel.add_user(user)
    user.channels.append(channel)

    user.enqueue(app.packets.channel_join(channel.name))

    channel_info_packet = app.packets.channel_info(channel)
    if channel.instance:
        for target in channel.users:
            target.enqueue(channel_info_packet)
    else:
        for target in app.state.sessions.users:
            if channel.has_permission(target.privileges):
                target.enqueue(channel_info_packet)

    log.info(f"{user} joined {channel}")
    return True


def leave_channel(user: User, channel: Channel, kick: bool = False) -> None:
    if user not in channel:
        return

    channel.remove_user(user)
    user.channels.remove(channel)

    if kick:
        user.enqueue(app.packets.channel_kick(channel.name))

    channel_info_packet = app.packets.channel_info(channel)
    if channel.instance:
        for user in channel.users:
            user.enqueue(channel_info_packet)
    else:
        for user in app.state.sessions.users:
            if channel.has_permission(user.privileges):
                user.enqueue(channel_info_packet)

    log.info(f"{user} left {channel}")


def add_spectator(user: User, other_user: User) -> None:
    spec_name = f"#spec_{user.id}"

    if not (spec_chan := app.state.sessions.channels[spec_name]):
        spec_chan = Channel(
            name="#spectator",
            topic=f"{user.name}'s spectator channel",
            auto_join=False,
            instance=True,
            real_name=spec_name,
        )

        join_channel(user, spec_chan)
        app.state.sessions.channels.append(spec_chan)

    if not join_channel(other_user, spec_chan):
        log.warning(f"{other_user} failed to join {spec_chan}")

    if not other_user.stealth:
        fellow_joined = app.packets.spectator_joined(other_user.id)

        for spec in user.spectators:
            spec.enqueue(fellow_joined)
            other_user.enqueue(app.packets.spectator_joined(spec.id))

        user.enqueue(app.packets.host_spectator_joined(other_user.id))
    else:
        for spec in user.spectators:
            other_user.enqueue(app.packets.spectator_joined(spec.id))

    user.spectators.append(other_user)
    other_user.spectating = user

    log.info(f"{other_user} started spectating {user}")


def remove_spectator(user: User, other_user: User) -> None:
    user.spectators.remove(other_user)
    other_user.spectating = None

    channel = app.state.sessions.channels[f"#spec_{user.id}"]
    leave_channel(other_user, channel)

    if not user.spectators:
        leave_channel(user, channel)
    else:
        channel_info = app.packets.channel_info(channel)
        fellow_packet = app.packets.spectator_left(other_user.id)

        user.enqueue(channel_info)
        for spec in user.spectators:
            spec.enqueue(fellow_packet + channel_info)

    user.enqueue(app.packets.host_spectator_left(other_user.id))
    log.info(f"{other_user} stopped spectating {user}")


async def update_activity(user: User) -> None:
    latest = int(time.time())

    user_collection = app.state.services.database.users
    await user_collection.update_one(
        {"id": user.id},
        {"$set": {"latest_activity": latest}},
    )

    user.latest_activity = latest


def update_status(user: User, action_struct: app.models.ChangeActionStructure) -> None:
    user.status.action = Action(action_struct.action)
    user.status.info_text = action_struct.info_text
    user.status.map_md5 = action_struct.map_md5
    user.status.mods = Mods(action_struct.mods)
    user.status.mode = Mode(action_struct.mode)
    user.status.map_id = action_struct.map_id

    if not user.restricted:
        app.state.sessions.users.enqueue(app.packets.user_stats(user))

    # TODO: update to redis or smth?


async def add_friend(user: User, other_user: User) -> None:
    if other_user.id in user.friends:
        log.warning(
            f"{user} tried to add {other_user} who is already in their friends list",
        )
        return

    user.friends.append(other_user.id)
    user_collection = app.state.services.database.users
    await user_collection.update_one(
        {"id": user.id},
        {"$push": {"friends": other_user.id}},
    )

    log.info(f"{user} added {other_user} to their friends list")


async def remove_friend(user: User, other_user: User) -> None:
    if other_user.id not in user.friends:
        log.warning(
            f"{user} tried to remove {other_user} who is not in their friends list",
        )
        return

    user.friends.append(other_user.id)
    user_collection = app.state.services.database.users
    await user_collection.update_one(
        {"id": user.id},
        {"$pull": {"friends": other_user.id}},
    )

    log.info(f"{user} removed {other_user} from their friends list")


async def handle_restriction(user: User) -> None:
    for mode in Mode:
        leaderboard_str = f"aisuru:leaderboard:{mode.value}"
        country_leaderboard_str = (
            f"{leaderboard_str}:{user.geolocation.country.acronym}"
        )

        stats = user.stats[mode]
        stats.global_rank = 0
        stats.country_rank = 0

        await app.state.services.redis.zrem(leaderboard_str, user.id)
        await app.state.services.redis.zrem(country_leaderboard_str, user.id)

    logout(user)  # reconnect them xd


async def handle_unrestriction(user: User) -> None:
    for mode in Mode:
        leaderboard_str = f"aisuru:leaderboard:{mode.value}"
        country_leaderboard_str = (
            f"{leaderboard_str}:{user.geolocation.country.acronym}"
        )

        stats = user.stats[mode]

        await app.state.services.redis.zadd(leaderboard_str, {user.id: stats.pp})
        await app.state.services.redis.zadd(
            country_leaderboard_str,
            {user.id: stats.pp},
        )

        global_rank = await app.state.services.redis.zrevrank(
            leaderboard_str,
            user.id,
        )
        if global_rank is not None:
            global_rank += 1
        else:
            global_rank = 0

        country_rank = await app.state.services.redis.zrevrank(
            country_leaderboard_str,
            user.id,
        )
        if country_rank is not None:
            country_rank += 1
        else:
            country_rank = 0

        stats.global_rank = global_rank
        stats.country_rank = country_rank

    logout(user)  # reconnect them xd


async def handle_freeze(user: User) -> None:
    user_collection = app.state.services.database.users
    _user = await user_collection.find_one({"id": user.id})

    user.freeze_timer = _user["freeze_timer"]

    logout(user)  # reconnect them xd


async def handle_unfreeze(user: User) -> None:
    user.freeze_timer = 0
    logout(user)  # reconnect them xd


async def set_privileges(user: User, privileges: Privileges) -> None:
    user.privileges = privileges

    user_collection = app.state.services.database.users
    await user_collection.update_one(
        {"id": user.id},
        {"$set": {"privileges": privileges}},
    )

    await app.state.services.redis.publish(
        "user-privileges",
        orjson.dumps({"id": user.id, "privileges": privileges.value}),
    )


async def add_privilege(user: User, privilege: Privileges) -> None:
    await set_privileges(user, user.privileges | privilege)


async def remove_privilege(user: User, privilege: Privileges) -> None:
    await set_privileges(user, user.privileges & ~privilege)


async def restrict(user: User, reason: str, sender: Optional[User] = None) -> None:
    if not sender:
        sender = app.state.sessions.bot

    logs_collection = app.state.services.database.logs
    await logs_collection.update_one(
        {"id": user.id},
        {
            "$addToSet": {
                "actions": {
                    "action": "restrict",
                    "sender": sender.name,
                    "info": reason,
                },
            },
        },
    )

    await add_privilege(user, Privileges.RESTRICTED)


async def unrestrict(user: User, reason: str, sender: Optional[User] = None) -> None:
    if not sender:
        sender = app.state.sessions.bot

    logs_collection = app.state.services.database.logs
    await logs_collection.update_one(
        {"id": user.id},
        {
            "$addToSet": {
                "actions": {
                    "action": "unrestrict",
                    "sender": sender.name,
                    "info": reason,
                },
            },
        },
    )

    await remove_privilege(user, Privileges.RESTRICTED)


async def freeze(user: User, reason: str, sender: Optional[User] = None) -> None:
    if not sender:
        sender = app.state.sessions.bot

    logs_collection = app.state.services.database.logs
    await logs_collection.update_one(
        {"id": user.id},
        {
            "$addToSet": {
                "actions": {
                    "action": "freeze",
                    "sender": sender.name,
                    "info": reason,
                },
            },
        },
    )

    user.freeze_timer = datetime.now() + timedelta(days=7)
    users_collection = app.state.services.database.users
    await users_collection.update_one(
        {"id": user.id},
        {
            "$set": {"freeze_timer": user.freeze_timer},
        },
    )

    await add_privilege(user, Privileges.FROZEN)


async def unfreeze(user: User, reason: str, sender: Optional[User] = None) -> None:
    if not sender:
        sender = app.state.sessions.bot

    logs_collection = app.state.services.database.logs
    await logs_collection.update_one(
        {"id": user.id},
        {
            "$addToSet": {
                "actions": {
                    "action": "unfreeze",
                    "sender": sender.name,
                    "info": reason,
                },
            },
        },
    )

    user.freeze_timer = 0
    users_collection = app.state.services.database.users
    await users_collection.update_one(
        {"id": user.id},
        {
            "$set": {"freeze_timer": user.freeze_timer},
        },
    )

    await remove_privilege(user, Privileges.FROZEN)
