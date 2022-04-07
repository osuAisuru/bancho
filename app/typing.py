from __future__ import annotations

import struct
from typing import Any
from typing import Awaitable
from typing import Callable
from typing import Optional
from typing import TYPE_CHECKING
from typing import TypedDict

from app.constants.action import ReplayAction
from app.constants.mode import Mode
from app.constants.mods import Mods
from app.objects.match import MatchTeams
from app.objects.match import MatchTeamTypes
from app.objects.match import MatchWinConditions
from app.objects.match import Slot
from app.objects.match import SlotStatus


class LoginData(TypedDict):
    username: str
    password_md5: bytes
    osu_version: str
    utc_offset: int
    display_city: bool
    pm_private: bool
    osu_path_md5: str
    adapters_str: str
    adapters_md5: str
    uninstall_md5: str
    disk_signature_md5: str


if TYPE_CHECKING:
    from app.packets import Packet

PacketHandler = Callable[
    [bytearray, Any],
    Awaitable[None],
]  # TODO: type-hint packet data


def read_int(data: bytearray, signed: bool = True) -> int:
    return int.from_bytes(data, "little", signed=signed)


def read_float(data: bytearray) -> float:
    return struct.unpack("<f", data)


class osuType:
    @classmethod
    def read(cls, packet: Packet) -> Any:
        ...

    @classmethod
    def write(cls, data: Any) -> bytearray:
        ...


class i8(osuType):
    @classmethod
    def read(cls, packet: Packet) -> int:
        return read_int(packet.read(1))

    @classmethod
    def write(cls, data: int) -> bytearray:
        return struct.pack("<b", data)


class u8(osuType):
    @classmethod
    def read(cls, packet: Packet) -> int:
        return read_int(packet.read(1), signed=False)

    @classmethod
    def write(cls, data: int) -> bytearray:
        return struct.pack("<B", data)


class i16(osuType):
    @classmethod
    def read(cls, packet: Packet) -> int:
        return read_int(packet.read(2))

    @classmethod
    def write(cls, data: int) -> bytearray:
        return struct.pack("<h", data)


class u16(osuType):
    @classmethod
    def read(cls, packet: Packet) -> int:
        return read_int(packet.read(2), signed=False)

    @classmethod
    def write(cls, data: int) -> bytearray:
        return struct.pack("<H", data)


class i32(osuType):
    @classmethod
    def read(cls, packet: Packet) -> int:
        return read_int(packet.read(4))

    @classmethod
    def write(cls, data: int) -> bytearray:
        return struct.pack("<i", data)


class i32_list(osuType):
    @classmethod
    def read(cls, packet: Packet) -> list[int]:
        length = i16.read(packet)
        return struct.unpack(
            f"<{'I' * length}",
            packet.read(length * 4),
        )

    @classmethod
    def write(cls, data: set[int]) -> bytearray:
        buffer = bytearray(len(data).to_bytes(2, "little"))

        for item in data:
            buffer += item.to_bytes(4, "little")

        return buffer


class u32(osuType):
    @classmethod
    def read(cls, packet: Packet) -> int:
        return read_int(packet.read(4), signed=False)

    @classmethod
    def write(cls, data: int) -> bytearray:
        return struct.pack("<I", data)


class f32(osuType):
    @classmethod
    def read(cls, packet: Packet) -> int:
        return read_float(packet.read(4))

    @classmethod
    def write(cls, data: float) -> bytearray:
        return struct.pack("<f", data)


class i64(osuType):
    @classmethod
    def read(cls, packet: Packet) -> int:
        return read_int(packet.read(8))

    @classmethod
    def write(cls, data: int) -> bytearray:
        return struct.pack("<q", data)


class f64(osuType):
    @classmethod
    def read(cls, packet: Packet) -> int:
        return read_float(packet.read(8))

    @classmethod
    def write(cls, data: float) -> bytearray:
        return struct.pack("<d", data)


class String(osuType):
    @classmethod
    def read(cls, packet: Packet) -> str:
        if u8.read(packet) != 0x0B:
            return ""

        length = shift = 0

        while True:
            body = u8.read(packet)

            length |= (body & 0b01111111) << shift
            if (body & 0b10000000) == 0:
                break

            shift += 7

        return packet.read(length).decode()

    @classmethod
    def write(cls, data: str) -> bytearray:
        encoded_string = data.encode()
        length = len(encoded_string)

        if length == 0:
            return bytearray(b"\x00")

        buffer = bytearray(b"\x0b")
        val = length

        while True:
            buffer.append(val & 0x7F)
            val >>= 7

            if val != 0:
                buffer[-1] |= 0x80
            else:
                break

        buffer += encoded_string
        return buffer


class Message(osuType):
    def __init__(
        self,
        sender_username: str,
        content: str,
        recipient_username: str,
        sender_id: int,
    ) -> None:
        self.sender_username = sender_username
        self.content = content
        self.recipient_username = recipient_username
        self.sender_id = sender_id

    @classmethod
    def read(cls, packet: Packet) -> Message:
        return Message(
            sender_username=String.read(packet),
            content=String.read(packet),
            recipient_username=String.read(packet),
            sender_id=i32.read(packet),
        )

    @classmethod
    def write(
        cls,
        sender_username: str,
        content: str,
        recipient_username: str,
        sender_id: int,
    ) -> bytearray:
        message = Message(sender_username, content, recipient_username, sender_id)

        return message.serialise()

    def serialise(self) -> bytearray:
        data = bytearray(String.write(self.sender_username))

        data += String.write(self.content)
        data += String.write(self.recipient_username)
        data += i32.write(self.sender_id)

        return data


class OsuChannel(osuType):
    def __init__(
        self,
        name: str,
        topic: str,
        player_count: int,
    ):
        self.name = name
        self.topic = topic
        self.player_count = player_count

    @classmethod
    def read(cls, packet: Packet) -> OsuChannel:
        return OsuChannel(
            name=String.read(packet),
            topic=String.read(packet),
            player_count=i32.read(packet),
        )

    @classmethod
    def write(
        cls,
        name: str,
        topic: str,
        player_count: int,
    ) -> bytearray:
        channel = OsuChannel(name, topic, player_count)

        return channel.serialise()

    def serialise(self) -> bytearray:
        data = bytearray(String.write(self.name))

        data += String.write(self.topic)
        data += i32.write(self.player_count)

        return data


SCOREFRAME_FMT = struct.Struct("<iBHHHHHHiHH?BB?")


class ScoreFrame(osuType):
    def __init__(
        self,
        time: int,
        id: int,
        num300: int,
        num100: int,
        num50: int,
        num_geki: int,
        num_katu: int,
        num_miss: int,
        total_score: int,
        current_combo: int,
        max_combo: int,
        perfect: bool,
        current_hp: int,
        tag_byte: int,
        score_v2: bool,
        combo_portion: Optional[float] = None,
        bonus_portion: Optional[float] = None,
    ):
        self.time = time
        self.id = id
        self.num300 = num300
        self.num100 = num100
        self.num50 = num50
        self.num_geki = num_geki
        self.num_katu = num_katu
        self.num_miss = num_miss
        self.total_score = total_score
        self.current_combo = current_combo
        self.max_combo = max_combo
        self.perfect = perfect
        self.current_hp = current_hp
        self.tag_byte = tag_byte

        self.score_v2 = score_v2

        self.combo_portion: Optional[float] = combo_portion
        self.bonus_portion: Optional[float] = bonus_portion

    @classmethod
    def read(cls, packet: Packet) -> ScoreFrame:
        # this is for speed, maybe ill write this out properly later
        data = packet.read(29)
        score_frame = ScoreFrame(*SCOREFRAME_FMT.unpack_from(data))

        if score_frame.score_v2:
            score_frame.combo_portion = f64.read(packet)
            score_frame.bonus_portion = f64.read(packet)

        return score_frame

    @classmethod
    def write(
        cls,
        time: int,
        id: int,
        num300: int,
        num100: int,
        num50: int,
        num_geki: int,
        num_katu: int,
        num_miss: int,
        total_score: int,
        current_combo: int,
        max_combo: int,
        perfect: bool,
        current_hp: int,
        tag_byte: int,
        score_v2: bool,
        combo_portion: Optional[float] = None,
        bonus_portion: Optional[float] = None,
    ):
        score_frame = ScoreFrame(
            time,
            id,
            num300,
            num100,
            num50,
            num_geki,
            num_katu,
            num_miss,
            total_score,
            current_combo,
            max_combo,
            perfect,
            current_hp,
            tag_byte,
            score_v2,
            combo_portion,
            bonus_portion,
        )

        return score_frame.serialise()

    def serialise(self) -> bytearray:
        return SCOREFRAME_FMT.pack(
            self.time,
            self.id,
            self.num300,
            self.num100,
            self.num50,
            self.num_geki,
            self.num_katu,
            self.num_miss,
            self.total_score,
            self.current_combo,
            self.max_combo,
            self.perfect,
            self.current_hp,
            self.tag_byte,
            self.score_v2,
        )


class ReplayFrame(osuType):
    def __init__(
        self,
        button_state: u8,
        taiko_byte: u8,
        x: f32,
        y: f32,
        time: i32,
    ):
        self.button_state = button_state
        self.taiko_byte = taiko_byte
        self.x = x
        self.y = y
        self.time = time

    @classmethod
    def read(cls, packet: Packet) -> ReplayFrame:
        return ReplayFrame(
            button_state=u8.read(packet),
            taiko_byte=u8.read(packet),
            x=f32.read(packet),
            y=f32.read(packet),
            time=i32.read(packet),
        )

    @classmethod
    def write(
        cls,
        button_state: u8,
        taiko_byte: u8,
        x: f32,
        y: f32,
        time: i32,
    ):
        frame = ReplayFrame(button_state, taiko_byte, x, y, time)

        return frame.serialise()

    def serialise(self) -> bytearray:
        data = bytearray(u8.write(self.button_state))

        data += u8.write(self.taiko_byte)
        data += u8.write(self.taiko_byte)
        data += f32.write(self.x)
        data += f32.write(self.y)
        data += i32.write(self.time)

        return data


class ReplayFrameBundle(osuType):
    def __init__(
        self,
        frames: list[ReplayFrame],
        score_frame: ScoreFrame,
        action: ReplayAction,
        extra: i32,  # ?
        sequence: u16,  # ?
        raw_data: bytearray,
    ) -> None:
        self.frames = frames
        self.score_frame = score_frame
        self.action = action
        self.extra = extra
        self.sequence = sequence
        self.raw_data = raw_data

    @classmethod
    def read(cls, packet: Packet) -> ReplayFrameBundle:
        raw_data = packet.data[: packet.length]  # slice to copy

        extra = i32.read(packet)
        frame_count = u16.read(packet)
        frames = [ReplayFrame.read() for _ in range(frame_count)]
        action = ReplayAction(u8.read(packet))
        score_frame = ReplayFrame.read(packet)
        sequence = u16.read(packet)

        return ReplayFrameBundle(frames, score_frame, action, extra, sequence, raw_data)

    @classmethod
    def write(
        cls,
        frames: list[ReplayFrame],
        score_frame: ScoreFrame,
        action: ReplayFrame,
        extra: i32,  # ?
        sequence: u16,  # ?
        raw_data: bytearray,
    ) -> bytearray:
        frame_bundle = ReplayFrameBundle(
            frames,
            score_frame,
            action,
            extra,
            sequence,
            raw_data,
        )

        return frame_bundle.serialise()

    def serialise(self) -> bytearray:
        data = bytearray(i32.write(self.extra))

        data += u16.write(len(self.frames))
        for frame in self.frames:
            data += frame.serialise()

        data += self.score_frame.serialise()
        data += u16.write(self.sequence)
        data += u8.write(self.action.value)

        return data


class OsuMatch(osuType):
    def __init__(
        self,
        id: int,
        in_progress: bool,
        mods: Mods,
        password: str,
        name: str,
        map_name: str,
        map_id: int,
        map_md5: str,
        slot_ids: list[int],
        win_condition: MatchWinConditions,
        team_type: MatchTeamTypes,
        freemod: bool,
        seed: int,
        slot_statuses: list[SlotStatus],
        slot_teams: list[MatchTeams],
        slot_mods: list[Mods],
        mode: Mode,
        host_id: int,
    ):
        self.id: int = id
        self.in_progress: bool = in_progress
        self.mods: Mods = mods
        self.password: str = password
        self.name: str = name
        self.map_name: str = map_name
        self.map_id: int = map_id
        self.map_md5: str = map_md5
        self.slot_ids: list[int] = slot_ids
        self.win_condition: MatchWinConditions = win_condition
        self.team_type: MatchTeamTypes = team_type
        self.freemod: bool = freemod
        self.seed: int = seed

        self.slot_statuses: list[SlotStatus] = slot_statuses
        self.slot_teams: list[MatchTeams] = slot_teams
        self.slot_mods: list[Mods] = slot_mods
        self.mode: Mode = mode
        self.host_id: int = host_id

    @classmethod
    def read(cls, packet: Packet) -> OsuMatch:
        match_id = i16.read(packet)
        in_progress = i8.read(packet) == 1
        powerplay = i8.read(packet)  # ?
        mods = Mods(i32.read(packet))
        name = String.read(packet)
        password = String.read(packet)
        map_name = String.read(packet)
        map_id = i32.read(packet)
        map_md5 = String.read(packet)
        slot_statuses = [SlotStatus(i8.read(packet)) for _ in range(16)]
        slot_teams = [MatchTeams(i8.read(packet)) for _ in range(16)]

        slot_ids = []
        for status in slot_statuses:
            if status & SlotStatus.HAS_USER:
                slot_ids.append(i32.read(packet))

        host_id = i32.read(packet)
        mode = Mode(i8.read(packet))
        win_condition = MatchWinConditions(i8.read(packet))
        team_type = MatchTeamTypes(i8.read(packet))
        freemod = i8.read(packet) == 1

        slot_mods = []
        if freemod:
            slot_mods = [Mods(i32.read(packet)) for _ in range(16)]

        seed = i32.read(packet)

        return OsuMatch(
            match_id,
            in_progress,
            mods,
            password,
            name,
            map_name,
            map_id,
            map_md5,
            slot_ids,
            win_condition,
            team_type,
            freemod,
            seed,
            slot_statuses,
            slot_teams,
            slot_mods,
            mode,
            host_id,
        )

    @classmethod
    def write(
        cls,
        id: int,
        in_progress: bool,
        mods: Mods,
        password: str,
        name: str,
        map_name: str,
        map_id: int,
        map_md5: str,
        slot_ids: list[int],
        win_condition: MatchWinConditions,
        team_type: MatchTeamTypes,
        freemod: bool,
        seed: int,
        slot_statuses: list[SlotStatus],
        slot_teams: list[MatchTeams],
        slot_mods: list[Mods],
        mode: Mode,
        host_id: int,
    ):
        match = OsuMatch(
            id,
            in_progress,
            mods,
            password,
            name,
            map_name,
            map_id,
            map_md5,
            slot_ids,
            win_condition,
            team_type,
            freemod,
            seed,
            slot_statuses,
            slot_teams,
            slot_mods,
            mode,
            host_id,
        )

        return match.serialise()

    def serialise(self, send_pw: bool = True) -> bytearray:
        data = bytearray(u16.write(self.id))

        data += i8.write(int(self.in_progress))
        data += i8.write(0)  # ?
        data += i32.write(self.mods.value)
        data += String.write(self.name)

        if self.password:
            if send_pw:
                data += String.write(self.password)
            else:
                data += b"\x0b\x00"
        else:
            data += b"\x00"

        data += String.write(self.map_name)
        data += i32.write(self.map_id)
        data += String.write(self.map_md5)

        data.extend([status.value for status in self.slot_statuses])
        data.extend([team.value for team in self.slot_teams])

        for idx, slot_status in enumerate(self.slot_statuses):
            if slot_status & SlotStatus.HAS_USER:
                data += i32.write(self.slot_ids[idx])

        data += i32.write(self.host_id)
        data += i8.write(self.mode.value)
        data += i8.write(self.win_condition.value)
        data += i8.write(self.team_type.value)
        data += i8.write(int(self.freemod))

        if self.freemod:
            for mod in self.slot_mods:
                data += i32.write(mod.value)

        data += i32.write(self.seed)

        return data
