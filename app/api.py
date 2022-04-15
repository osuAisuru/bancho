from __future__ import annotations

import re
import time
from datetime import date
from datetime import timedelta
from typing import Any
from typing import Literal
from typing import Optional
from typing import TYPE_CHECKING
from typing import TypedDict

from fastapi import APIRouter
from fastapi import Request
from fastapi.param_functions import Header
from fastapi.responses import HTMLResponse
from fastapi.responses import Response

import log
from app.constants.mods import Mods
from app.constants.privileges import BanchoPrivileges
from app.constants.privileges import Privileges
from app.objects.channel import Channel
from app.objects.match import MatchTeams
from app.objects.match import MatchTeamTypes
from app.objects.match import Slot
from app.objects.match import SlotStatus
from app.objects.user import ClientInfo
from app.objects.user import OsuVersion

if TYPE_CHECKING:
    from app.objects.user import User

import app.usecases
import app.packets
import app.state
import app.models
import app.config
import app.utils
from app.state.services import Geolocation
from app.typing import LoginData, Message, PacketHandler, i32

router = APIRouter(tags=["Bancho API"])


@router.get("/")
async def index_html() -> HTMLResponse:
    return HTMLResponse("and why are you here?")


class LoginResponse(TypedDict):
    token: str
    body: bytearray


def parse_login_data(data: bytes) -> LoginData:
    (
        username,
        password_md5,
        remainder,
    ) = data.decode().split("\n", maxsplit=2)

    (
        osu_version,
        utc_offset,
        display_city,
        client_hashes,
        pm_private,
    ) = remainder.split("|", maxsplit=4)

    (
        osu_path_md5,
        adapters_str,
        adapters_md5,
        uninstall_md5,
        disk_signature_md5,
    ) = client_hashes[:-1].split(":", maxsplit=4)

    return {
        "username": username,
        "password_md5": password_md5.encode(),
        "osu_version": osu_version,
        "utc_offset": int(utc_offset),
        "display_city": display_city == "1",
        "pm_private": pm_private == "1",
        "osu_path_md5": osu_path_md5,
        "adapters_str": adapters_str,
        "adapters_md5": adapters_md5,
        "uninstall_md5": uninstall_md5,
        "disk_signature_md5": disk_signature_md5,
    }


OSU_VERSION = re.compile(
    r"^b(?P<date>\d{8})(?:\.(?P<revision>\d))?"
    r"(?P<stream>beta|cuttingedge|dev|tourney)?$",
)
DELTA_90_DAYS = timedelta(days=90)


def parse_osu_version(osu_version: str) -> Optional[OsuVersion]:
    ver_match = OSU_VERSION.match(osu_version)
    if ver_match is None:
        return None

    osu_ver = OsuVersion(
        date=date(
            year=int(ver_match["date"][0:4]),
            month=int(ver_match["date"][4:6]),
            day=int(ver_match["date"][6:8]),
        ),
        revision=int(ver_match["revision"]) if ver_match["revision"] else None,
        stream=ver_match["stream"] or "stable",
    )

    # TODO: check & cache latest version instead of allowing certain ranges
    if osu_ver.date < (date.today() - DELTA_90_DAYS):
        return None  # is this misleading?

    return osu_ver


def parse_adapters(adapters_str: str) -> Optional[tuple[list[str], bool]]:
    running_under_wine = adapters_str == "runningunderwine"
    adapters = [adapter for adapter in adapters_str[:-1].split(".")]

    if not (running_under_wine or any(adapters)):
        return None, running_under_wine

    return adapters, running_under_wine


@router.post("/")
async def bancho_handler(
    request: Request,
    osu_token: Optional[str] = Header(None),
    user_agent: Literal["osu!"] = Header(...),
) -> Response:
    geoloc = Geolocation.from_ip(request.headers)
    body = await request.body()

    if not osu_token:
        async with app.state.sessions.users.lock:
            login_data = await login(body, geoloc)

        return Response(
            content=bytes(login_data["body"]),
            headers={"cho-token": login_data["token"]},
        )

    # user already logged in
    user = await app.usecases.user.fetch(token=osu_token)

    if not user:
        # server probably restarted, lets send restart packet

        return Response(content=bytes(app.packets.restart_server(0)))

    packet_map = app.state.PACKETS
    if user.restricted:
        packet_map = app.state.RESTRICTED_PACKETS

    for packet, handler in app.packets.PacketArray(bytearray(body), packet_map):
        await handler(packet, user)

        if (
            osu_packet := app.packets.Packets(packet.packet_id)
        ) is not app.packets.Packets.OSU_PING:
            log.debug(f"Packet {osu_packet!r} handled for {user}")

    await app.usecases.user.update_activity(user)
    return Response(user.dequeue())


RESTRICTION_MESSAGE = "Your account is currently in restricted mode. Please check the website for more information!"
WELCOME_MESSAGE = "Welcome to Aisuru!"

# TODO: webhook some of these invalid requests/inputs passed thru login & packets


async def login(
    body: bytes,
    geoloc: Geolocation,
) -> LoginData:
    start = time.perf_counter_ns()

    login_data = parse_login_data(body)

    osu_version = parse_osu_version(login_data["osu_version"])
    if not osu_version:
        return {
            "token": "no",
            "body": app.packets.version_update_forced() + app.packets.user_id(-2),
        }

    if logged_user := await app.usecases.user.fetch(name=login_data["username"]):
        if not (osu_version.stream == "tourney" or logged_user.tourney):
            if (time.time() - logged_user.latest_activity) > 10:
                app.usecases.user.logout(logged_user)
            else:
                return {
                    "token": "no",
                    "body": app.packets.notification("You are already logged in!"),
                }

    adapters, running_under_wine = parse_adapters(login_data["adapters_str"])
    if not adapters and not running_under_wine:
        return {
            "token": "no",
            "body": app.packets.user_id(-5),  # not strictly an old client
        }

    client_info = ClientInfo(
        client=osu_version,
        osu_md5=login_data["osu_path_md5"],
        adapters_md5=login_data["adapters_md5"],
        uninstall_md5=login_data["uninstall_md5"],
        disk_md5=login_data["disk_signature_md5"],
        adapters=adapters,
    )

    user = await app.usecases.user.create_session(login_data, geoloc, client_info)
    if not user:
        return {
            "token": "no",
            "body": app.packets.user_id(-1),
        }

    if not await app.usecases.password.verify_password(
        login_data["password_md5"],
        user.password_bcrypt,
    ):
        return {
            "token": "no",
            "body": app.packets.user_id(-1),
        }

    await app.usecases.user.save_login(user)

    hw_checks = {"userid": {"$ne": user.id}}
    if running_under_wine:
        hw_checks["uninstall"] = client_info.adapters_md5
    else:
        hw_checks |= {
            "adapters": client_info.adapters_md5,
            "uninstall": client_info.uninstall_md5,
            "disk": client_info.disk_md5,
        }

    hashes_collection = app.state.services.database.client_hashes
    hw_matches = await hashes_collection.find(hw_checks).to_list(length=None)

    if hw_matches:  # TODO: restrict & webhook
        hw_str = ", ".join(str(hw_match["userid"]) for hw_match in hw_matches)
        log.warning(
            f"{user.name} has tried to log in on matching hardware with users: {hw_str}",
        )

        return {
            "token": "no",
            "body": app.packets.user_id(-1)
            + app.packets.notification(f"Please contact staff."),
        }

    if osu_version.stream == "tourney":
        if not user.can_tourney:
            return {
                "token": "no",
                "body": app.packets.user_id(-5),  # is this the error i want to use?
            }
        else:
            user.tourney = True

    data = bytearray(app.packets.protocol_version(19))
    data += app.packets.user_id(user.id)
    data += app.packets.bancho_privileges(
        user.bancho_privileges | BanchoPrivileges.SUPPORTER,
    )

    for channel in app.state.sessions.channels:
        if (
            not channel.auto_join
            or not channel.has_permission(user.privileges)
            or channel.name == "#lobby"
        ):
            continue

        channel_info_packet = app.packets.channel_info(channel)
        data += channel_info_packet

        for target in app.state.sessions.users:
            if channel.has_permission(target.privileges):
                target.enqueue(channel_info_packet)

    data += app.packets.channel_info_end()
    data += app.packets.menu_icon(
        app.config.MAIN_MENU_ICON_URL,
        app.config.MAIN_MENU_CLICK_URL,
    )
    data += app.packets.friends_list(user.friends)
    data += app.packets.silence_end(user.remaining_silence)

    user_data = app.packets.user_presence(user) + app.packets.user_stats(user)
    data += user_data

    for target in app.state.sessions.users:
        if not user.restricted:
            target.enqueue(user_data)

        if not target.restricted:
            data += app.packets.user_presence(target) + app.packets.user_stats(target)

    if user.restricted:
        data += app.packets.user_restricted()
        data += app.packets.send_message(
            Message(
                app.state.sessions.bot.name,
                RESTRICTION_MESSAGE,
                user.name,
                app.state.sessions.bot.id,
            ),
        )

    if not user.privileges & Privileges.VERIFIED:
        await app.usecases.user.add_privilege(user, Privileges.VERIFIED)

        if user.id == 3:
            await app.usecases.user.set_privileges(user, Privileges.MASTER)

        data += app.packets.send_message(
            Message(
                app.state.sessions.bot.name,
                WELCOME_MESSAGE,
                user.name,
                app.state.sessions.bot.id,
            ),
        )

    app.state.sessions.users.append(user)

    end = time.perf_counter_ns()
    formatted_time = log.format_time(end - start)

    data += app.packets.notification(
        f"Welcome back to Aisuru!\n\n"
        f"Online users: {len(app.state.sessions.users) - 1}\n"
        f"Time elapsed: {formatted_time}",
    )

    log.info(
        f"{user.name} logged in with osu! version {user.client_info.client} from {user.geolocation.country.acronym.upper()} in {formatted_time}",
    )

    await app.usecases.user.update_activity(user)
    user.login_time = int(time.time())

    return {
        "token": user.token,
        "body": data,
    }


def register_packet(_packet: app.packets.Packets, allow_restricted: bool = False):
    def decorator(handler: PacketHandler):
        async def wrapper(
            packet: app.packets.Packet,
            user: "User",
            packet_data: Any = None,
        ) -> None:
            structure = handler.__annotations__.get("packet_data")

            if structure:
                structure_class = app.utils.get_class_from_module(structure)

                data = structure_class()

                for field, _type in structure_class.__annotations__.items():
                    if _type in ("bytearray", "bytes"):
                        data.__dict__[field] = packet.data
                    else:
                        _type_class = app.utils.get_class_from_module(_type)
                        data.__dict__[field] = _type_class.read(packet)

                return await handler(
                    user,
                    data,
                )  # async def handler(user: User, packet_data: StructureClass) -> None

            # no data, just pass player
            return await handler(user)  # async def handler(user: User) -> None

        packet_id = int(_packet)
        app.state.PACKETS[packet_id] = wrapper
        if allow_restricted:
            app.state.RESTRICTED_PACKETS[packet_id] = wrapper

        return wrapper

    return decorator


@register_packet(app.packets.Packets.OSU_CHANGE_ACTION, allow_restricted=True)
async def change_action(
    user: "User",
    packet_data: app.models.ChangeActionStructure,
) -> None:
    app.usecases.user.update_status(user, packet_data)


IGNORED_CHANNELS = ["#highlight", "#userlog"]


@register_packet(app.packets.Packets.OSU_SEND_PUBLIC_MESSAGE)
async def send_public_message(
    user: "User",
    packet_data: app.models.SendMessageStructure,
) -> None:
    if user.silenced:
        log.warning(f"{user} tried to send a message while silenced")
        return

    msg = packet_data.message.content.strip()
    if not msg:
        return

    recipient = packet_data.message.recipient_username
    if recipient in IGNORED_CHANNELS:
        return

    if recipient == "#spectator":
        if user.spectating:
            spec_id = user.spectating.id
        else:
            spec_id = user.id

        target_channel = app.state.sessions.channels[f"#spec_{spec_id}"]
    elif recipient == "#multiplayer":
        if not user.match:
            return

        target_channel = user.match.chat
    else:
        target_channel = app.state.sessions.channels[recipient]

    if not target_channel:
        log.warning(f"{user} tried to write to non-existant channel {recipient}")
        return

    if user not in target_channel:
        log.warning(f"{user} tried to write in {recipient} without being in it")
        return

    if not target_channel.has_permission(user.privileges):
        log.warning(f"{user} tried to write in {recipient} without permission")
        return

    # TODO: commands

    target_channel.send(msg, user)
    await app.usecases.user.update_activity(user)

    log.info(f"{user} sent a message to {recipient}: {msg}", file="logs/chat.log")


@register_packet(app.packets.Packets.OSU_LOGOUT, allow_restricted=True)
async def logout(user: "User") -> None:
    if int(time.time()) - user.login_time < 1:
        return  # just osu things

    app.usecases.user.logout(user)
    await app.usecases.user.update_activity(user)


@register_packet(app.packets.Packets.OSU_REQUEST_STATUS_UPDATE, allow_restricted=True)
async def request_status_update(user: "User") -> None:
    user.enqueue(app.packets.user_stats(user))


@register_packet(app.packets.Packets.OSU_START_SPECTATING)
async def start_spectating(
    user: "User",
    packet_data: app.models.StartSpectatingStructure,
) -> None:
    if not (host := await app.usecases.user.fetch(id=packet_data.target_id)):
        log.warning(
            f"{user} tried to spectate non-existent user ID {packet_data.target_id}",
        )
        return

    if existing_host := user.spectating:
        if existing_host == host:
            if not user.stealth:
                host.enqueue(app.packets.host_spectator_joined(user.id))

                fellow_joined = app.packets.spectator_joined(user.id)
                for spec in host.spectators:
                    if spec is not user:
                        user.enqueue(fellow_joined)

            return

        app.usecases.user.remove_spectator(existing_host, user)

    app.usecases.user.add_spectator(host, user)


@register_packet(app.packets.Packets.OSU_STOP_SPECTATING)
async def stop_spectating(user: "User") -> None:
    if not user.spectating:
        log.warning(
            f"{user} tried to stop spectating when they aren't spectating anyone",
        )
        return

    app.usecases.user.remove_spectator(user.spectating, user)


@register_packet(app.packets.Packets.OSU_SPECTATE_FRAMES)
async def spectate_frames(
    user: "User",
    packet_data: app.models.SpectateFramesStructure,
) -> None:
    if not user.spectating:
        log.warning(
            f"{user} tried to get spectate frames when they aren't spectating anyone",
        )
        return

    spec_frames = app.packets.spectate_frames(user.id, packet_data.frames)
    for target in user.spectators:
        target.enqueue(spec_frames)


@register_packet(app.packets.Packets.OSU_CANT_SPECTATE)
async def cant_spectate(user: "User") -> None:
    if not user.spectating:
        log.warning(
            f"{user} tried to spectate when they aren't spectating anyone",
        )
        return

    if not user.stealth:
        data = app.packets.cant_spectate(user.id)

        user.spectating.enqueue(data)
        for target in user.spectating.spectators:
            target.enqueue(data)


@register_packet(app.packets.Packets.OSU_SEND_PRIVATE_MESSAGE)
async def private_message(
    user: "User",
    packet_data: app.models.SendMessageStructure,
) -> None:
    if user.silenced:
        log.warning(f"{user} tried to send a message while silenced")
        return

    msg = packet_data.message.content.strip()
    if not msg:
        return

    target_name = packet_data.message.recipient_username
    if not (target := await app.usecases.user.fetch(name=target_name)):
        log.warning(
            f"{user} tried to send a message to non-existent user {target_name}",
        )
        return

    if user.id in target.blocked:
        user.enqueue(app.packets.private_message_blocked(target_name))

        log.warning(
            f"{user} tried to send a message to {target_name} but they are blocked",
        )
        return

    if target.friend_only_dms and user.id not in target.friends:
        user.enqueue(app.packets.private_message_blocked(target_name))

        log.warning(
            f"{user} tried to send a message to non-mutual {target_name} but they have friend only DMs enabled",
        )
        return

    if target.silenced:
        user.enqueue(app.packets.target_silenced(target_name))

        log.warning(
            f"{user} tried to send a message to {target_name} while they are silenced",
        )
        return

    # TODO: commands

    target.receive_message(msg, user)
    await app.usecases.user.update_activity(user)

    log.info(f"{user} sent a message to {target}: {msg}", file="logs/chat.log")


@register_packet(app.packets.Packets.OSU_CHANNEL_JOIN)
async def join_channel(
    user: "User",
    packet_data: app.models.ChannelStructure,
) -> None:
    if packet_data.channel_name in IGNORED_CHANNELS:
        return

    channel = app.state.sessions.channels[packet_data.channel_name]
    if not channel:
        log.warning(f"{user} failed to join {channel}")
        return

    app.usecases.user.join_channel(user, channel)


@register_packet(app.packets.Packets.OSU_FRIEND_ADD)
async def add_friend(
    user: "User",
    packet_data: app.models.FriendStructure,
) -> None:
    if not (target := await app.usecases.user.fetch(id=packet_data.target_id)):
        log.warning(
            f"{user} tried to friend non-existent user ID {packet_data.target_id}",
        )
        return

    if target is app.state.sessions.bot:
        return

    if user.id in target.blocked:
        log.warning(f"{user} tried to add {target}, but they are blocked")
        return

    await app.usecases.user.update_activity(user)
    await app.usecases.user.add_friend(user, target)


@register_packet(app.packets.Packets.OSU_FRIEND_ADD)
async def remove_friend(
    user: "User",
    packet_data: app.models.FriendStructure,
) -> None:
    if not (target := await app.usecases.user.fetch(id=packet_data.target_id)):
        log.warning(
            f"{user} tried to unfriend non-existent user ID {packet_data.target_id}",
        )
        return

    if target is app.state.sessions.bot:
        return

    await app.usecases.user.update_activity(user)
    await app.usecases.user.remove_friend(user, target)


@register_packet(app.packets.Packets.OSU_CHANNEL_PART)
async def leave_channel(
    user: "User",
    packet_data: app.models.ChannelStructure,
) -> None:
    if packet_data.channel_name in IGNORED_CHANNELS:
        return

    channel = app.state.sessions.channels[packet_data.channel_name]
    if not channel:
        if packet_data.channel_name[0] == "#":
            log.warning(f"{user} tried to leave non-existant channel {channel}")

        return

    if user not in channel:
        log.warning(f"{user} tried to leave {channel} without being in it")
        return

    app.usecases.user.leave_channel(user, channel)


@register_packet(app.packets.Packets.OSU_USER_STATS_REQUEST)
async def stats_request(
    user: "User",
    packet_data: app.models.StatsRequestStructure,
) -> None:
    unrestricted_ids = [user.id for user in app.state.sessions.users.unrestricted]
    is_online = lambda u: u in unrestricted_ids and u != user.id

    for online_user in filter(is_online, packet_data.user_ids):
        target = await app.usecases.user.fetch(id=online_user)
        if not target:
            continue  # ?, should not happen

        user.enqueue(app.packets.user_stats(target))


@register_packet(app.packets.Packets.OSU_USER_PRESENCE_REQUEST)
async def user_presence_request(
    user: "User",
    packet_data: app.models.UserPresenceRequestStructure,
) -> None:
    unrestricted_ids = [user.id for user in app.state.sessions.users.unrestricted]
    is_online = lambda u: u in unrestricted_ids and u != user.id

    for online_user in filter(is_online, packet_data.user_ids):
        target = await app.usecases.user.fetch(id=online_user)
        if not target:
            continue

        user.enqueue(app.packets.user_presence(target))


@register_packet(app.packets.Packets.OSU_USER_PRESENCE_REQUEST_ALL)
async def user_presence_request_all(user: "User") -> None:
    buffer = bytearray()

    for u in app.state.sessions.users.unrestricted:
        buffer += app.packets.user_presence(u)

    user.enqueue(buffer)


@register_packet(app.packets.Packets.OSU_TOGGLE_BLOCK_NON_FRIEND_DMS)
async def toggle_dms(user: "User", packet_data: app.models.ToggleDMStructure) -> None:
    user.friend_only_dms = packet_data.value == 1
    await app.usecases.user.update_activity(user)


@register_packet(app.packets.Packets.OSU_JOIN_LOBBY)
async def join_lobby(user: "User") -> None:
    user.in_lobby = True

    for match in app.state.sessions.matches:
        if match is not None:
            user.enqueue(app.packets.new_match(match))


@register_packet(app.packets.Packets.OSU_CREATE_MATCH)
async def create_match(user: "User", packet_data: app.models.MatchStructure) -> None:
    match = app.usecases.match.from_packet(packet_data.match)

    if user.silenced:
        user.enqueue(
            app.packets.match_join_fail()
            + app.packets.notification("Multiplayer is not available while silenced."),
        )

        return

    if not app.state.sessions.matches.append(match):
        user.receive_message(
            "Failed to create match (no slots are left)",
            app.state.sessions.bot,
        )
        user.enqueue(app.packets.match_join_fail())

        return

    channel = Channel(
        name="#multiplayer",
        topic=f"Match ID {match.id}'s multiplayer channel",
        auto_join=False,
        instance=True,
        real_name=f"#multi_{match.id}",
    )

    app.state.sessions.channels.append(channel)
    match.chat = channel

    await app.usecases.user.update_activity(user)
    app.usecases.user.join_match(user, match, match.password)

    log.info(f"{user} created new multiplayer match {match}")


@register_packet(app.packets.Packets.OSU_JOIN_MATCH)
async def join_match(user: "User", packet_data: app.models.JoinMatchStructure) -> None:
    if user.silenced:
        user.enqueue(
            app.packets.match_join_fail()
            + app.packets.notification("Multiplayer is not available while silenced."),
        )

        return

    if not (match := app.state.sessions.matches[packet_data.match_id]):
        log.warning(
            f"{user} tried to join non-existent match ID {packet_data.match_id}",
        )
        user.enqueue(app.packets.match_join_fail())

    await app.usecases.user.update_activity(user)
    app.usecases.user.join_match(user, match, packet_data.match_password)


@register_packet(app.packets.Packets.OSU_PART_MATCH)
async def leave_match(user: "User") -> None:
    await app.usecases.user.update_activity(user)
    app.usecases.user.leave_match(user)


@register_packet(app.packets.Packets.OSU_MATCH_CHANGE_SLOT)
async def change_match_slot(
    user: "User",
    packet_data: app.models.MatchSlotStructure,
) -> None:
    if not (match := user.match):
        return

    if not 0 <= packet_data.slot_id < 16:
        return

    if match.slots[packet_data.slot_id] != SlotStatus.OPEN:
        log.warning(f"{user} tried to move into a non-open slot")
        return

    slot = match.get_slot(user)
    assert slot is not None

    match.slots[packet_data.slot_id].copy_from(slot)
    slot.reset()

    app.usecases.match.enqueue_state(match)


@register_packet(app.packets.Packets.OSU_MATCH_READY)
async def match_ready(user: "User") -> None:
    if not (match := user.match):
        return

    slot = match.get_slot(user)
    assert slot is not None

    slot.status = SlotStatus.READY
    app.usecases.match.enqueue_state(match)


@register_packet(app.packets.Packets.OSU_MATCH_LOCK)
async def lock_match(user: "User", packet_data: app.models.MatchSlotStructure) -> None:
    if not (match := user.match):
        return

    if user is not app.usecases.match.host(match):
        log.warning(f"{user} tried to lock match slot as non-host")
        return

    if not 0 <= packet_data.slot_id < 16:
        return

    slot = match.slots[packet_data.slot_id]
    if slot.status == SlotStatus.LOCKED:
        slot.status = SlotStatus.OPEN
    else:
        if slot.user is app.usecases.match.host(match):
            return

        slot.status = SlotStatus.LOCKED

    app.usecases.match.enqueue_state(match)


@register_packet(app.packets.Packets.OSU_MATCH_CHANGE_SETTINGS)
async def change_match_settings(
    user: "User",
    packet_data: app.models.MatchStructure,
) -> None:
    if not (match := user.match):
        return

    if user is not app.usecases.match.host(match):
        log.warning(f"{user} tried to change match settings as non-host")
        return

    if packet_data.match.freemod != match.freemod:
        match.freemod = packet_data.match.freemod

        if packet_data.match.freemod:
            for slot in match.slots:
                if slot.status & SlotStatus.HAS_USER:
                    slot.mods = match.mods & ~Mods.SPEED_MODS

            match.mods &= Mods.SPEED_MODS
        else:
            host = app.usecases.match.get_host_slot(match)
            assert host is not None

            host.mods &= Mods.SPEED_MODS
            match.mods |= host.mods

            for slot in match.slots:
                if slot.status & SlotStatus.HAS_USER:
                    slot.mods = Mods.NOMOD

    if packet_data.match.map_id == -1:
        match.unready_users()
        match.last_map_id = match.map_id

        match.map_id = -1
        match.map_md5 = ""
        match.map_name = ""
    elif match.map_id == -1:
        # TODO: get/validate beatmap from api

        match.map_id = packet_data.match.map_id
        match.map_md5 = packet_data.match.map_md5
        match.map_name = packet_data.match.map_name
        match.mode = packet_data.match.mode

        if match.last_map_id != packet_data.match.map_id:
            match.chat.send(f"Selected: {match.map_embed}", app.state.sessions.bot)

    if match.team_type != packet_data.match.team_type:
        if packet_data.match.team_type in (
            MatchTeamTypes.HEAD_TO_HEAD,
            MatchTeamTypes.TAG_COOP,
        ):
            new_type = MatchTeams.NEUTRAL
        else:
            new_type = MatchTeams.RED

        for slot in match.slots:
            if slot.status & SlotStatus.HAS_USER:
                slot.team = new_type

        match.team_type = packet_data.match.team_type

    match.win_condition = packet_data.match.win_condition
    match.name = packet_data.match.name

    app.usecases.match.enqueue_state(match)


@register_packet(app.packets.Packets.OSU_MATCH_START)
async def start_match(user: "User") -> None:
    if not (match := user.match):
        return

    if user is not app.usecases.match.host(match):
        log.warning(f"{user} tried to start match as non-host")
        return

    app.usecases.match.start(match)


@register_packet(app.packets.Packets.OSU_MATCH_SCORE_UPDATE)
async def update_match_score(
    user: "User",
    packet_data: app.models.RawStructure,
) -> None:
    if not (match := user.match):
        return

    # raw write for speed, this is called often
    data = bytearray(b"0\x00\x00")
    data += i32.write(len(packet_data.data))
    data += packet_data.data
    data[11] = match.get_slot_id(user)

    app.usecases.match.enqueue(match, data, lobby=False)


@register_packet(app.packets.Packets.OSU_MATCH_COMPLETE)
async def match_complete(user: "User") -> None:
    if not (match := user.match):
        return

    slot = match.get_slot(user)
    assert slot is not None

    slot.status = SlotStatus.COMPLETE

    if any(slot.status == SlotStatus.PLAYING for slot in match.slots):
        return

    not_playing = [
        slot.user.id
        for slot in match.slots
        if slot.status & SlotStatus.HAS_USER and slot.status != SlotStatus.COMPLETE
    ]

    match.unready_users(expected=SlotStatus.COMPLETE)
    match.in_progress = False

    app.usecases.match.enqueue(
        match,
        app.packets.match_complete(),
        lobby=False,
        immune=not_playing,
    )
    app.usecases.match.enqueue_state(match)


@register_packet(app.packets.Packets.OSU_MATCH_CHANGE_MODS)
async def change_match_mods(
    user: "User",
    packet_data: app.models.MatchModsStructure,
) -> None:
    if not (match := user.match):
        return

    if match.freemod:
        if user is app.usecases.match.host(match):
            match.mods = Mods(packet_data.mods & Mods.SPEED_MODS)

        slot = match.get_slot(user)
        assert slot is not None
        slot.mods = Mods(packet_data.mods & ~Mods.SPEED_MODS)
    else:
        if user is not app.usecases.match.host(match):
            log.warning(f"{user} tried to change mods as non-host")
            return

        match.mods = Mods(packet_data.mods)

    app.usecases.match.enqueue_state(match)


def is_playing(slot: Slot) -> bool:
    return slot.status == SlotStatus.PLAYING and not slot.loaded


@register_packet(app.packets.Packets.OSU_MATCH_LOAD_COMPLETE)
async def match_load_complete(user: "User") -> None:
    if not (match := user.match):
        return

    slot = match.get_slot(user)
    assert slot is not None

    slot.loaded = True
    if not any(map(is_playing, match.slots)):
        app.usecases.match.enqueue(
            match,
            app.packets.match_all_players_loaded(),
            lobby=False,
        )


@register_packet(app.packets.Packets.OSU_MATCH_NO_BEATMAP)
async def missing_beatmap(user: "User") -> None:
    if not (match := user.match):
        return

    slot = match.get_slot(user)
    assert slot is not None

    slot.status = SlotStatus.NO_MAP
    app.usecases.match.enqueue_state(match, lobby=False)


@register_packet(app.packets.Packets.OSU_MATCH_NOT_READY)
async def match_unready(user: "User") -> None:
    if not (match := user.match):
        return

    slot = match.get_slot(user)
    assert slot is not None

    slot.status = SlotStatus.NOT_READY
    app.usecases.match.enqueue_state(match, lobby=False)


@register_packet(app.packets.Packets.OSU_MATCH_FAILED)
async def match_failed(user: "User") -> None:
    if not (match := user.match):
        return

    slot_id = match.get_slot_id(user)
    assert slot_id is not None

    app.usecases.match.enqueue(
        match,
        app.packets.match_player_failed(slot_id),
        lobby=False,
    )


@register_packet(app.packets.Packets.OSU_MATCH_HAS_BEATMAP)
async def has_beatmap(user: "User") -> None:
    if not (match := user.match):
        return

    slot = match.get_slot(user)
    assert slot is not None

    slot.status = SlotStatus.NOT_READY
    app.usecases.match.enqueue_state(match, lobby=False)


@register_packet(app.packets.Packets.OSU_MATCH_SKIP_REQUEST)
async def match_skip_request(user: "User") -> None:
    if not (match := user.match):
        return

    slot = match.get_slot(user)
    assert slot is not None

    slot.skipped = True
    app.usecases.match.enqueue(app.packets.match_player_skipped(user.id))

    for slot in match.slots:
        if slot.status == SlotStatus.PLAYING and not slot.skipped:
            return

    app.usecases.match.enqueue(app.packets.match_skip(), lobby=False)


@register_packet(app.packets.Packets.OSU_MATCH_TRANSFER_HOST)
async def transfer_host(
    user: "User",
    packet_data: app.models.MatchSlotStructure,
) -> None:
    if not (match := user.match):
        return

    if user is not app.usecases.match.host(match):
        log.warning(f"{user} tried to transfer host as non-host")
        return

    if not 0 <= packet_data.slot_id < 16:
        return

    if not (target := match.slots[packet_data.slot_id].user):
        log.warning(f"{user} tried to transfer host to empty slot")
        return

    match.host_id = target.id
    app.usecases.match.host(match).enqueue(app.packets.match_transfer_host())
    app.usecases.match.enqueue_state(match)


@register_packet(app.packets.Packets.OSU_TOURNAMENT_MATCH_INFO_REQUEST)
async def tourney_match_info(
    user: "User",
    packet_data: app.models.MatchIDSStructure,
) -> None:
    if not 0 <= packet_data.match_id < 64:
        return

    if not user.privileges & Privileges.SUPPORTER:
        return

    if not (match := app.state.sessions.matches[packet_data.match_id]):
        return

    user.enqueue(app.packets.update_match(match, send_pw=False))


@register_packet(app.packets.Packets.OSU_TOURNAMENT_JOIN_MATCH_CHANNEL)
async def tourney_join_channel(
    user: "User",
    packet_data: app.models.MatchIDSStructure,
) -> None:
    if not 0 <= packet_data.match_id < 64:
        return

    if not user.privileges & Privileges.SUPPORTER:
        return

    if not (match := app.state.sessions.matches[packet_data.match_id]):
        return

    for slot in match.slots:
        if slot.user is not None and slot.user.id == user.id:
            return

    if app.usecases.user.join_channel(user, match.chat):
        match.tourney_clients.add(user.id)


@register_packet(app.packets.Packets.OSU_TOURNAMENT_LEAVE_MATCH_CHANNEL)
async def tourney_leave_channel(
    user: "User",
    packet_data: app.models.MatchIDSStructure,
) -> None:
    if not 0 <= packet_data.match_id < 64:
        return

    if not user.privileges & Privileges.SUPPORTER:
        return

    if not (match := app.state.sessions.matches[packet_data.match_id]):
        return

    app.usecases.user.leave_channel(user, match.chat)
    match.tourney_clients.remove(user.id)


@register_packet(app.packets.Packets.OSU_MATCH_CHANGE_TEAM)
async def change_match_team(user: "User") -> None:
    if not (match := user.match):
        return

    slot = match.get_slot(user)
    assert slot is not None

    if slot.team == MatchTeams.BLUE:
        slot.team = MatchTeams.RED
    else:
        slot.team = MatchTeams.BLUE

    app.usecases.match.enqueue_state(match, lobby=False)


@register_packet(app.packets.Packets.OSU_MATCH_INVITE)
async def match_invite(
    user: "User",
    packet_data: app.models.MatchInviteStructure,
) -> None:
    if not user.match:
        return

    if not (target := app.usecases.user.cache_fetch(id=packet_data.user_id)):
        log.warning(
            f"{user} tried to invite user ID {packet_data.user_id} to a multi while they are offline",
        )
        return

    if target is app.state.sessions.bot:
        return

    target.enqueue(app.packets.match_invite(user, target.name))
    await app.usecases.user.update_activity(user)

    log.info(f"{user} invited {target} to their match")


@register_packet(app.packets.Packets.OSU_MATCH_CHANGE_PASSWORD)
async def change_match_password(
    user: "User",
    packet_data: app.models.MatchStructure,
) -> None:
    if not (match := user.match):
        return

    if user is not app.usecases.match.host(match):
        log.warning(f"{user} tried to change match password as non-host")
        return

    match.password = packet_data.match.password
    app.usecases.match.enqueue_state(match)


# XX: do i care about presence filter or away messages?
