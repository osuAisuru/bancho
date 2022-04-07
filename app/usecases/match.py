from __future__ import annotations

from typing import Optional

import app.packets
import app.state
import app.usecases
from app.constants.mods import Mods
from app.objects.match import Match
from app.objects.match import MatchTeams
from app.objects.match import Slot
from app.objects.match import SlotStatus
from app.objects.user import User
from app.typing import OsuMatch


def start(match: Match) -> None:
    missing_map: list[int] = []

    for slot in match.slots:
        if slot.status & SlotStatus.HAS_USER:
            if slot.status != SlotStatus.NO_MAP:
                slot.status = SlotStatus.PLAYING
            else:
                missing_map.append(slot.user.id)

    match.in_progress = True
    enqueue(match, app.packets.match_start(match), immune=missing_map, lobby=False)
    enqueue_state(match)


def enqueue(
    match: Match,
    data: bytes,
    lobby: bool = True,
    immune: list[int] = [],
):
    match.chat.enqueue(data, immune)

    if (
        lobby
        and (lobby_chat := app.state.sessions.channels["#lobby"])
        and lobby_chat.users
    ):
        lobby_chat.enqueue(data)


def enqueue_state(match: Match, lobby: bool = True) -> None:
    match.chat.enqueue(app.packets.update_match(match, send_pw=True))

    if (
        lobby
        and (lobby_chat := app.state.sessions.channels["#lobby"])
        and lobby_chat.users
    ):
        lobby_chat.enqueue(app.packets.update_match(match, send_pw=False))


def from_packet(packet_match: OsuMatch) -> Match:
    match = Match()

    match.mods = packet_match.mods

    match.name = packet_match.name
    match.password = packet_match.password

    match.map_name = packet_match.map_name
    match.map_id = packet_match.map_id
    match.map_md5 = packet_match.map_md5

    for slot, status, team, mods in zip(
        match.slots,
        packet_match.slot_statuses,
        packet_match.slot_teams,
        packet_match.slot_mods or [Mods.NOMOD] * 16,  # mods can be empty
    ):
        slot.status = status
        slot.team = team
        slot.mods = mods

    match.host_id = packet_match.host_id

    match.mode = packet_match.mode
    match.win_condition = packet_match.win_condition
    match.team_type = packet_match.team_type
    match.freemod = packet_match.freemod
    match.seed = packet_match.seed

    return match


def host(match: Match) -> User:
    user = app.usecases.user.cache_fetch(id=match.host_id)

    assert user is not None  # optional bad here
    return user


def refs(match: Match) -> set[User]:
    refs = match._refs

    host = host(match)
    if host is not None:
        refs.add(host)

    return refs


def get_host_slot(match: Match) -> Optional[Slot]:
    for slot in match.slots:
        if slot.status & SlotStatus.HAS_USER and slot.user is host(match):
            return slot
