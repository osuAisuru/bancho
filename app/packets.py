from __future__ import annotations

import struct
from enum import IntEnum
from functools import cache
from functools import lru_cache
from typing import Iterator
from typing import TYPE_CHECKING

from app.constants.action import Action
from app.constants.mode import Mode
from app.constants.mods import Mods

if TYPE_CHECKING:
    from app.objects.channel import Channel
    from app.objects.match import Match
    from app.objects.user import User

from app.typing import OsuChannel, OsuMatch
from app.typing import f32
from app.typing import i16
from app.typing import i32
from app.typing import i32_list
from app.typing import i64
from app.typing import Message
from app.typing import PacketHandler
from app.typing import String
from app.typing import u32
from app.typing import u8


class Packet:
    def __init__(self, packet_id: int, length: int, data: bytearray):
        self.data: bytearray = data
        self.packet_id: int = packet_id
        self.length: int = length

    def read_header(self) -> None:
        array = self.read(7)
        data = struct.unpack("<HxI", array)

        self.packet_id = data[0]
        self.length = data[1]

    @classmethod
    def from_data(self, data: bytearray) -> Packet:
        packet = Packet(0, 0, data)

        packet.read_header()
        return packet

    @classmethod
    def from_id(self, packet_id: int) -> Packet:
        return Packet(packet_id, 0, bytearray())

    def offset(self, count: int) -> None:
        self.data = self.data[count:]

    def read(self, count: int) -> bytearray:
        data = self.data[:count]
        self.offset(count)

        return data

    def __iadd__(self, other: bytearray) -> Packet:
        self.write(other)
        return self

    def write(self, data: bytearray) -> None:
        self.data += data

    def serialise(self) -> bytearray:
        return_data = bytearray()

        return_data += i16.write(self.packet_id)
        return_data += u8.write(0)  # padding byte

        # actual packet data
        return_data += u32.write(len(self.data))
        return_data += self.data

        return return_data


def parse_header(data: bytearray) -> tuple[int, int]:
    header = data[:7]
    data = struct.unpack("<HxI", header)

    return data[0], data[1]  # packet id, length


class PacketArray:
    def __init__(self, data: bytearray, packet_map: dict[int, PacketHandler]) -> None:
        self.data = data
        self.packets: list[Packet] = []
        self.packet_map = packet_map

        self._split_data()

    def __iter__(self) -> Iterator[tuple[Packet, PacketHandler]]:
        for packet in self.packets:
            handler = self.packet_map[packet.packet_id]

            yield packet, handler

    def _split_data(self) -> None:
        while self.data:
            packet_id, length = parse_header(self.data)

            if packet_id not in self.packet_map.keys():
                self.data = self.data[7 + length :]
                continue

            packet_data = self.data[: 7 + length]
            packet = Packet.from_data(packet_data)
            self.packets.append(packet)

            self.data = self.data[7 + length :]


class Packets(IntEnum):
    OSU_CHANGE_ACTION = 0
    OSU_SEND_PUBLIC_MESSAGE = 1
    OSU_LOGOUT = 2
    OSU_REQUEST_STATUS_UPDATE = 3
    OSU_PING = 4
    CHO_USER_ID = 5
    CHO_SEND_MESSAGE = 7
    CHO_PONG = 8
    CHO_HANDLE_IRC_CHANGE_USERNAME = 9
    CHO_HANDLE_IRC_QUIT = 10
    CHO_USER_STATS = 11
    CHO_USER_LOGOUT = 12
    CHO_SPECTATOR_JOINED = 13
    CHO_SPECTATOR_LEFT = 14
    CHO_SPECTATE_FRAMES = 15
    OSU_START_SPECTATING = 16
    OSU_STOP_SPECTATING = 17
    OSU_SPECTATE_FRAMES = 18
    CHO_VERSION_UPDATE = 19
    OSU_ERROR_REPORT = 20
    OSU_CANT_SPECTATE = 21
    CHO_SPECTATOR_CANT_SPECTATE = 22
    CHO_GET_ATTENTION = 23
    CHO_NOTIFICATION = 24
    OSU_SEND_PRIVATE_MESSAGE = 25
    CHO_UPDATE_MATCH = 26
    CHO_NEW_MATCH = 27
    CHO_DISPOSE_MATCH = 28
    OSU_PART_LOBBY = 29
    OSU_JOIN_LOBBY = 30
    OSU_CREATE_MATCH = 31
    OSU_JOIN_MATCH = 32
    OSU_PART_MATCH = 33
    CHO_TOGGLE_BLOCK_NON_FRIEND_DMS = 34
    CHO_MATCH_JOIN_SUCCESS = 36
    CHO_MATCH_JOIN_FAIL = 37
    OSU_MATCH_CHANGE_SLOT = 38
    OSU_MATCH_READY = 39
    OSU_MATCH_LOCK = 40
    OSU_MATCH_CHANGE_SETTINGS = 41
    CHO_FELLOW_SPECTATOR_JOINED = 42
    CHO_FELLOW_SPECTATOR_LEFT = 43
    OSU_MATCH_START = 44
    CHO_ALL_PLAYERS_LOADED = 45
    CHO_MATCH_START = 46
    OSU_MATCH_SCORE_UPDATE = 47
    CHO_MATCH_SCORE_UPDATE = 48
    OSU_MATCH_COMPLETE = 49
    CHO_MATCH_TRANSFER_HOST = 50
    OSU_MATCH_CHANGE_MODS = 51
    OSU_MATCH_LOAD_COMPLETE = 52
    CHO_MATCH_ALL_PLAYERS_LOADED = 53
    OSU_MATCH_NO_BEATMAP = 54
    OSU_MATCH_NOT_READY = 55
    OSU_MATCH_FAILED = 56
    CHO_MATCH_PLAYER_FAILED = 57
    CHO_MATCH_COMPLETE = 58
    OSU_MATCH_HAS_BEATMAP = 59
    OSU_MATCH_SKIP_REQUEST = 60
    CHO_MATCH_SKIP = 61
    CHO_UNAUTHORIZED = 62  # unused
    OSU_CHANNEL_JOIN = 63
    CHO_CHANNEL_JOIN_SUCCESS = 64
    CHO_CHANNEL_INFO = 65
    CHO_CHANNEL_KICK = 66
    CHO_CHANNEL_AUTO_JOIN = 67
    OSU_BEATMAP_INFO_REQUEST = 68
    CHO_BEATMAP_INFO_REPLY = 69
    OSU_MATCH_TRANSFER_HOST = 70
    CHO_PRIVILEGES = 71
    CHO_FRIENDS_LIST = 72
    OSU_FRIEND_ADD = 73
    OSU_FRIEND_REMOVE = 74
    CHO_PROTOCOL_VERSION = 75
    CHO_MAIN_MENU_ICON = 76
    OSU_MATCH_CHANGE_TEAM = 77
    OSU_CHANNEL_PART = 78
    OSU_RECEIVE_UPDATES = 79
    CHO_MONITOR = 80  # unused
    CHO_MATCH_PLAYER_SKIPPED = 81
    OSU_SET_AWAY_MESSAGE = 82
    CHO_USER_PRESENCE = 83
    OSU_IRC_ONLY = 84
    OSU_USER_STATS_REQUEST = 85
    CHO_RESTART = 86
    OSU_MATCH_INVITE = 87
    CHO_MATCH_INVITE = 88
    CHO_CHANNEL_INFO_END = 89
    OSU_MATCH_CHANGE_PASSWORD = 90
    CHO_MATCH_CHANGE_PASSWORD = 91
    CHO_SILENCE_END = 92
    OSU_TOURNAMENT_MATCH_INFO_REQUEST = 93
    CHO_USER_SILENCED = 94
    CHO_USER_PRESENCE_SINGLE = 95
    CHO_USER_PRESENCE_BUNDLE = 96
    OSU_USER_PRESENCE_REQUEST = 97
    OSU_USER_PRESENCE_REQUEST_ALL = 98
    OSU_TOGGLE_BLOCK_NON_FRIEND_DMS = 99
    CHO_USER_DM_BLOCKED = 100
    CHO_TARGET_IS_SILENCED = 101
    CHO_VERSION_UPDATE_FORCED = 102
    CHO_SWITCH_SERVER = 103
    CHO_ACCOUNT_RESTRICTED = 104
    CHO_RTX = 105  # unused
    CHO_MATCH_ABORT = 106
    CHO_SWITCH_TOURNAMENT_SERVER = 107
    OSU_TOURNAMENT_JOIN_MATCH_CHANNEL = 108
    OSU_TOURNAMENT_LEAVE_MATCH_CHANNEL = 109

    def __repr__(self) -> str:
        return f"<{self.name} ({self.value})>"


@cache
def pong() -> bytearray:
    packet = Packet.from_id(Packets.CHO_PONG)
    return packet.serialise()


@cache
def user_id(id: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_USER_ID)
    packet += i32.write(id)
    return packet.serialise()


@cache
def protocol_version(version: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_PROTOCOL_VERSION)
    packet += i32.write(version)
    return packet.serialise()


@cache
def bancho_privileges(priv: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_PRIVILEGES)
    packet += i32.write(priv)
    return packet.serialise()


def bot_presence(user: User) -> bytearray:
    packet = Packet.from_id(Packets.CHO_USER_PRESENCE)

    packet += i32.write(user.id)
    packet += String.write(user.name)
    packet += u8.write(24)  # utc offset
    packet += u8.write(user.geolocation.country.code)
    packet += u8.write(user.bancho_privileges)
    packet += f32.write(user.geolocation.long)
    packet += f32.write(user.geolocation.lat)
    packet += i32.write(0)  # rank

    return packet.serialise()


def user_presence(user: User) -> bytearray:
    if user.id == 1:
        return bot_presence(user)

    packet = Packet.from_id(Packets.CHO_USER_PRESENCE)

    packet += i32.write(user.id)
    packet += String.write(user.name)
    packet += u8.write(user.utc_offset + 24)
    packet += u8.write(user.geolocation.country.code)
    packet += u8.write(user.bancho_privileges | (user.status.mode.as_vn << 5))
    packet += f32.write(user.geolocation.long)
    packet += f32.write(user.geolocation.lat)
    packet += i32.write(user.current_stats.global_rank)

    return packet.serialise()


def bot_stats(user: User) -> bytearray:
    packet = Packet.from_id(Packets.CHO_USER_STATS)

    packet += i32.write(user.id)
    packet += u8.write(Action.WATCHING.value)
    packet += String.write("over Aisuru")
    packet += String.write("")  # map md5
    packet += i32.write(Mods.NOMOD.value)
    packet += u8.write(Mode.STD.value)
    packet += i32.write(0)  # map id
    packet += i64.write(0)  # ranked score
    packet += f32.write(0.0)  # accuracy
    packet += i32.write(0)  # playcount
    packet += i64.write(0)  # total score
    packet += i32.write(0)  # rank
    packet += i16.write(0)  # pp

    return packet.serialise()


def user_stats(user: User) -> bytearray:
    if user.id == 1:
        return bot_stats(user)

    packet = Packet.from_id(Packets.CHO_USER_STATS)

    stats = user.current_stats
    if stats.pp > 0x7FFF:
        rscore = stats.pp
        pp = 0
    else:
        rscore = stats.ranked_score
        pp = stats.pp

    packet += i32.write(user.id)
    packet += u8.write(user.status.action.value)
    packet += String.write(user.status.info_text)
    packet += String.write(user.status.map_md5)
    packet += i32.write(user.status.mods.value)
    packet += u8.write(user.status.mode.as_vn)
    packet += i32.write(user.status.map_id)
    packet += i64.write(rscore)
    packet += f32.write(stats.accuracy / 100.0)
    packet += i32.write(stats.playcount)
    packet += i64.write(stats.total_score)
    packet += i32.write(stats.global_rank)
    packet += i16.write(pp)

    return packet.serialise()


@lru_cache(maxsize=4)
def notification(msg: str) -> bytearray:
    packet = Packet.from_id(Packets.CHO_NOTIFICATION)
    packet += String.write(msg)
    return packet.serialise()


@cache
def channel_info_end() -> bytearray:
    packet = Packet.from_id(Packets.CHO_CHANNEL_INFO_END)
    return packet.serialise()


@cache
def restart_server(time: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_RESTART)
    packet += i32.write(time)
    return packet.serialise()


@cache
def menu_icon(icon_url: str, click_url: str) -> bytearray:
    packet = Packet.from_id(Packets.CHO_MAIN_MENU_ICON)
    packet += String.write(f"{icon_url}|{click_url}")  # TODO: implement
    return packet.serialise()


def friends_list(friends_list: set[int]) -> bytearray:
    packet = Packet.from_id(Packets.CHO_FRIENDS_LIST)
    packet += i32_list.write(friends_list)
    return packet.serialise()


@cache
def silence_end(time: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_SILENCE_END)
    packet += i32.write(time)
    return packet.serialise()


def send_message(message: Message) -> bytearray:
    packet = Packet.from_id(Packets.CHO_SEND_MESSAGE)
    packet += message.serialise()
    return packet.serialise()


@cache
def logout(user_id: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_USER_LOGOUT)

    packet += i32.write(user_id)
    packet += u8.write(0)  # ?

    return packet.serialise()


@cache
def block_dm() -> bytearray:
    packet = Packet.from_id(Packets.CHO_USER_DM_BLOCKED)
    return packet.serialise()


@cache
def spectator_joined(user_id: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_FELLOW_SPECTATOR_JOINED)
    packet += i32.write(user_id)
    return packet.serialise()


@cache
def host_spectator_joined(user_id: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_SPECTATOR_JOINED)
    packet += i32.write(user_id)
    return packet.serialise()


@cache
def spectator_left(user_id: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_FELLOW_SPECTATOR_LEFT)
    packet += i32.write(user_id)
    return packet.serialise()


@cache
def host_spectator_left(user_id: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_SPECTATOR_LEFT)
    packet += i32.write(user_id)
    return packet.serialise()


def spectate_frames(frames: bytes) -> bytearray:
    packet = Packet.from_id(Packets.CHO_SPECTATE_FRAMES)
    packet += frames
    return packet.serialise()


@cache
def cant_spectate(user_id: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_SPECTATOR_CANT_SPECTATE)
    packet += i32.write(user_id)
    return packet.serialise()


@lru_cache(maxsize=8)
def join_channel(channel: str) -> bytearray:
    packet = Packet.from_id(Packets.CHO_CHANNEL_JOIN_SUCCESS)
    packet += String.write(channel)
    return packet.serialise()


def channel_info(channel: Channel) -> bytearray:
    packet = Packet.from_id(Packets.CHO_CHANNEL_INFO)

    osu_channel = OsuChannel(channel.name, channel.topic, channel.user_count)
    packet += osu_channel.serialise()

    return packet.serialise()


@lru_cache(maxsize=8)
def channel_kick(channel: str) -> bytearray:
    packet = Packet.from_id(Packets.CHO_CHANNEL_KICK)
    packet += String.write(channel)
    return packet.serialise()


@lru_cache(maxsize=16)
def channel_join(channel: str) -> bytearray:
    packet = Packet.from_id(Packets.CHO_CHANNEL_JOIN_SUCCESS)
    packet += String.write(channel)
    return packet.serialise()


@cache
def version_update_forced() -> bytearray:
    packet = Packet.from_id(Packets.CHO_VERSION_UPDATE_FORCED)
    return packet.serialise()


@cache
def user_restricted() -> bytearray:
    packet = Packet.from_id(Packets.CHO_ACCOUNT_RESTRICTED)
    return packet.serialise()


@lru_cache(maxsize=8)
def target_silenced(target_name: str) -> bytearray:
    packet = Packet.from_id(Packets.CHO_TARGET_IS_SILENCED)
    packet += Message.write("", "", target_name, 0)
    return packet.serialise()


@lru_cache(maxsize=8)
def private_message_blocked(target_name: str) -> bytearray:
    packet = Packet.from_id(Packets.CHO_USER_DM_BLOCKED)
    packet += Message.write("", "", target_name, 0)
    return packet.serialise()


def write_match(match: Match) -> OsuMatch:
    return OsuMatch(
        match.id,
        match.in_progress,
        match.mods,
        match.password,
        match.name,
        match.map_name,
        match.map_id,
        match.map_md5,
        [slot.user.id for slot in match.slots if slot.user],
        match.win_condition,
        match.team_type,
        match.freemod,
        match.seed,
        [slot.status for slot in match.slots],
        [slot.team for slot in match.slots],
        [slot.mods for slot in match.slots],
        match.mode,
        match.host_id,
    )


def update_match(match: Match, send_pw: bool = True) -> bytearray:
    packet = Packet.from_id(Packets.CHO_UPDATE_MATCH)

    osu_match = write_match(match)

    packet += osu_match.serialise(send_pw)
    return packet.serialise()


def match_start(match: Match) -> bytearray:
    packet = Packet.from_id(Packets.CHO_MATCH_START)

    osu_match = write_match(match)

    packet += osu_match.serialise()
    return packet.serialise()


def new_match(match: Match) -> bytearray:
    packet = Packet.from_id(Packets.CHO_NEW_MATCH)

    osu_match = write_match(match)

    packet += osu_match.serialise()
    return packet.serialise()


@cache
def match_join_fail() -> bytearray:
    packet = Packet.from_id(Packets.CHO_MATCH_JOIN_FAIL)
    return packet.serialise()


def match_join_success(match: Match) -> bytearray:
    packet = Packet.from_id(Packets.CHO_MATCH_JOIN_SUCCESS)

    osu_match = write_match(match)

    packet += osu_match.serialise()
    return packet.serialise()


@cache
def dispose_match(match_id: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_DISPOSE_MATCH)
    packet += i32.write(match_id)
    return packet.serialise()


@cache
def match_transfer_host() -> bytearray:
    packet = Packet.from_id(Packets.CHO_MATCH_TRANSFER_HOST)
    return packet.serialise()


@cache
def match_complete() -> bytearray:
    packet = Packet.from_id(Packets.CHO_MATCH_COMPLETE)
    return packet.serialise()


@cache
def match_all_players_loaded() -> bytearray:
    packet = Packet.from_id(Packets.CHO_MATCH_ALL_PLAYERS_LOADED)
    return packet.serialise()


@cache
def match_player_failed(slot_id: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_MATCH_PLAYER_FAILED)
    packet += i32.write(slot_id)
    return packet.serialise()


@cache
def match_player_skipped(user_id: int) -> bytearray:
    packet = Packet.from_id(Packets.CHO_MATCH_PLAYER_SKIPPED)
    packet += i32.write(user_id)
    return packet.serialise()


@cache
def match_skip() -> bytearray:
    packet = Packet.from_id(Packets.CHO_MATCH_SKIP)
    return packet.serialise()


def match_invite(user: User, target_name: str) -> bytearray:
    invite_text = f"Join my multiplayer match: {user.match.embed}"

    packet = Packet.from_id(Packets.CHO_MATCH_INVITE)
    packet += Message.write(
        user.name,
        invite_text,
        target_name,
        user.id,
    )

    return packet.serialise()
