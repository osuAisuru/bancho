from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import app.models
import app.packets
import app.state
import log
from app.constants.action import Action
from app.constants.mode import Mode
from app.constants.mods import Mods
from app.constants.privileges import BanchoPrivileges
from app.constants.privileges import Privileges
from app.constants.status import Status
from app.objects.channel import Channel
from app.objects.stats import Stats
from app.state.services import Geolocation
from app.typing import Message


@dataclass
class User:
    id: int
    name: str
    safe_name: str

    password_bcrypt: str
    register_time: int
    latest_activity: int
    email: str

    privileges: Privileges
    silence_end: int

    geolocation: Geolocation
    utc_offset: int
    osu_version: str
    status: Status
    login_time: int

    token: str
    queue: bytearray

    stats: dict[Mode, Stats]
    friends: list[int]

    channels: list[Channel]

    spectating: Optional[User]
    spectators: list[User]

    stealth: bool
    in_lobby: bool

    def __repr__(self) -> str:
        return f"<{self.name} ({self.id})>"

    @property
    def current_stats(self) -> Stats:
        return self.stats[self.status.mode]

    @property
    def bancho_privileges(self) -> BanchoPrivileges:
        privileges = BanchoPrivileges(0)

        if not self.privileges & Privileges.DISALLOWED:
            privileges |= BanchoPrivileges.PLAYER

        if self.privileges & Privileges.SUPPORTER:
            privileges |= BanchoPrivileges.SUPPORTER

        if self.privileges & Privileges.ADMIN:
            privileges |= BanchoPrivileges.MODERATOR

        if self.privileges & Privileges.DEVELOPER:
            privileges |= BanchoPrivileges.DEVELOPER

        if self.privileges & Privileges.OWNER:
            privileges |= BanchoPrivileges.OWNER

        return privileges

    @property
    def remaining_silence(self) -> int:
        return max(0, int(self.silence_end - time.time()))

    @property
    def silenced(self) -> bool:
        return self.remaining_silence != 0

    @property
    def restricted(self) -> bool:
        return self.privileges & Privileges.DISALLOWED

    @property
    def banned(self) -> bool:
        return self.privileges & Privileges.BANNED

    def enqueue(self, data: bytes) -> None:
        self.queue += data

    def dequeue(self) -> Optional[bytes]:
        if self.queue:
            data = bytes(self.queue)
            self.queue.clear()

            return data

    async def set_privileges(self, privileges: Privileges) -> None:
        self.privileges = privileges

        user_collection = app.state.services.database.users
        await user_collection.update_one(
            {"id": self.id},
            {"$set": {"privileges": privileges}},
        )

    async def add_privilege(self, privilege: Privileges) -> None:
        await self.set_privileges(self.privileges | privilege)

    def join_channel(self, channel: Channel) -> bool:
        if (
            self in channel
            or not channel.has_permission(self.privileges)
            or channel.name == "#lobby"
            and not self.in_lobby
        ):
            return False

        channel.add_user(self)
        self.channels.append(channel)

        self.enqueue(app.packets.channel_join(channel.name))

        channel_info_packet = app.packets.channel_info(channel)
        if channel.instance:
            for user in channel.users:
                user.enqueue(channel_info_packet)
        else:
            for user in app.state.sessions.users:
                if channel.has_permission(user.privileges):
                    user.enqueue(channel_info_packet)

        log.info(f"{self} joined {channel}")
        return True

    def leave_channel(self, channel: Channel, kick: bool = False) -> None:
        if self not in channel:
            return

        channel.remove_user(self)
        self.channels.remove(channel)

        if kick:
            self.enqueue(app.packets.channel_kick(channel.name))

        channel_info_packet = app.packets.channel_info(channel)
        if channel.instance:
            for user in channel.users:
                user.enqueue(channel_info_packet)
        else:
            for user in app.state.sessions.users:
                if channel.has_permission(user.privileges):
                    user.enqueue(channel_info_packet)

        log.info(f"{self} left {channel}")

    def add_spectator(self, user: User) -> None:
        spec_name = f"#spec_{self.id}"

        if not (spec_chan := app.state.sessions.channels[spec_name]):
            spec_chan = Channel(
                name="#spectator",
                topic=f"{self.name}'s spectator channel",
                auto_join=False,
                instance=True,
                real_name=spec_name,
            )

            self.join_channel(spec_chan)
            app.state.sessions.channels.append(spec_chan)

        if not user.join_channel(spec_chan):
            log.warning(f"{user} failed to join {spec_chan}")

        if not user.stealth:
            fellow_joined = app.packets.spectator_joined(user.id)

            for spec in self.spectators:
                spec.enqueue(fellow_joined)
                user.enqueue(app.packets.spectator_joined(spec.id))

            self.enqueue(app.packets.host_spectator_joined(user.id))
        else:
            for spec in self.spectators:
                user.enqueue(app.packets.spectator_joined(spec.id))

        self.spectators.append(user)
        user.spectating = self

        log.info(f"{user} started spectating {self}")

    def remove_spectator(self, user: User) -> None:
        self.spectators.remove(user)
        user.spectating = None

        channel = app.state.sessions.channels[f"#spec_{self.id}"]
        user.leave_channel(channel)

        if not self.spectators:
            self.leave_channel(channel)
        else:
            channel_info = app.packets.channel_info(channel)
            fellow_packet = app.packets.spectator_left(user.id)

            self.enqueue(channel_info)
            for spec in self.spectators:
                spec.enqueue(fellow_packet + channel_info)

        self.enqueue(app.packets.host_spectator_left(user.id))
        log.info(f"{user} stopped spectating {self}")

    def receive_message(self, msg_content: str, sender: User) -> None:
        self.enqueue(
            app.packets.send_message(
                Message(
                    sender.name,
                    msg_content,
                    self.name,
                    sender.id,
                ),
            ),
        )

    async def update_activity(self) -> None:
        user_collection = app.state.services.database.users
        await user_collection.update_one(
            {"id": self.id},
            {"$set": {"latest_activity": int(time.time())}},
        )

    def update_status(self, action_struct: app.models.ChangeActionStructure) -> None:
        self.status.action = Action(action_struct.action)
        self.status.info_text = action_struct.info_text
        self.status.map_md5 = action_struct.map_md5
        self.status.mods = Mods(action_struct.mods)
        self.status.mode = Mode(action_struct.mode)
        self.status.map_id = action_struct.map_id

        if not self.restricted:
            app.state.sessions.users.enqueue(app.packets.user_stats(self))

        # TODO: update to redis or smth?
