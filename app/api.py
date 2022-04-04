from __future__ import annotations

import time
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
from app.constants.privileges import BanchoPrivileges
from app.constants.privileges import Privileges

if TYPE_CHECKING:
    from app.objects.user import User

import app.usecases
import app.packets
import app.state
import app.models
import app.utils
from app.state.services import Geolocation
from app.typing import LoginData, Message, PacketHandler

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


@router.post("/")
async def bancho_handler(
    request: Request,
    osu_token: Optional[str] = Header(None),
    user_agent: Literal["osu!"] = Header(...),
) -> Response:
    geoloc = Geolocation.from_ip(request.headers)
    body = await request.body()

    if not osu_token:
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

    await user.update_activity()
    return Response(user.dequeue())


RESTRICTION_MESSAGE = "Your account is currently in restricted mode. Please check the website for more information!"
WELCOME_MESSAGE = "Welcome to Aisuru!"


async def login(
    body: bytes,
    geoloc: Geolocation,
) -> LoginData:
    start = time.perf_counter_ns()

    login_data = parse_login_data(body)
    if await app.usecases.user.fetch(name=login_data["username"]):
        return {
            "token": "no",
            "body": app.packets.notification("You are already logged in!"),
        }

    user = await app.usecases.user.create_session(login_data, geoloc)
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
    data += app.packets.menu_icon()
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
        await user.add_privilege(Privileges.VERIFIED)

        if user.id == 3:
            await user.set_privileges(Privileges.MASTER)

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
        f"{user.name} logged in with osu! version {user.osu_version} from {user.geolocation.country.acronym.upper()} in {formatted_time}",
    )

    await user.update_activity()
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
    user.update_status(packet_data)


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
        return  # TODO
    else:
        target_channel = app.state.sessions.channels[recipient]

    if not target_channel:
        log.warning(f"{user} tried to write to non-existant channel {recipient}")
        return

    if user not in target_channel:
        log.warning(f"{user} tried to write in {recipient} without being in it")
        return

    if not target_channel.has_permission(user):
        log.warning(f"{user} tried to write in {recipient} without permission")
        return

    # TODO: commands

    target_channel.send(msg, user)
    await user.update_activity()

    log.info(f"{user} sent a message to {recipient}: {msg}", file="logs/chat.log")


@register_packet(app.packets.Packets.OSU_LOGOUT, allow_restricted=True)
async def logout(user: "User") -> None:
    if int(time.time()) - user.login_time < 1:
        return  # just osu things

    app.usecases.user.logout(user)
    await user.update_activity()


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

        existing_host.remove_spectator(user)

    host.add_spectator(user)


@register_packet(app.packets.Packets.OSU_STOP_SPECTATING)
async def stop_spectating(user: "User") -> None:
    if not user.spectating:
        log.warning(
            f"{user} tried to stop spectating when they aren't spectating anyone",
        )
        return

    user.spectating.remove_spectator(user)


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

    # TODO: blocked users, private dms

    if target.silenced:
        user.enqueue(app.packets.target_silenced(target_name))

        log.warning(
            f"{user} tried to send a message to {target_name} while they are silenced",
        )
        return

    # TODO: commands

    target.receive_message(msg, user)
    await user.update_activity()

    log.info(f"{user} sent a message to {target}: {msg}", file="logs/chat.log")


@register_packet(app.packets.Packets.OSU_CHANNEL_JOIN)
async def join_channel(
    user: "User",
    packet_data: app.models.ChannelStructure,
) -> None:
    if packet_data.channel_name in IGNORED_CHANNELS:
        return

    channel = app.state.sessions.channels[packet_data.channel_name]
    if not channel or not user.join_channel(channel):
        log.warning(f"{user} failed to join {channel}")


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

    # TODO: blocked users

    await user.update_activity()
    await user.add_friend(target)


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

    await user.update_activity()
    await user.remove_friend(target)


@register_packet(app.packets.Packets.OSU_CHANNEL_PART)
async def leave_channel(
    user: "User",
    packet_data: app.models.ChannelStructure,
) -> None:
    if packet_data.channel_name in IGNORED_CHANNELS:
        return

    channel = app.state.sessions.channels[packet_data.channel_name]
    if not channel or user not in channel:
        log.warning(f"{user} failed to leave {channel}")

    user.leave_channel(channel)


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


# XX: do i care about presence filter or away messages?
# TODO: match stuff
