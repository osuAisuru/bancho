from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Optional

from aiohttp import ClientSession
from fastapi import status

import app.config
import app.state
from app.constants.mode import Mode
from app.objects.beatmap import Beatmap
from app.objects.beatmap import RankedStatus


async def fetch_by_md5(md5: str) -> Optional[Beatmap]:
    if beatmap := await md5_from_database(md5):
        return beatmap

    if beatmap := await md5_from_api(md5):
        return beatmap


async def fetch_by_id(id: int) -> Optional[Beatmap]:
    if beatmap := await id_from_database(id):
        return beatmap

    if beatmap := await id_from_api(id):
        return beatmap


async def fetch_by_set_id(set_id: int) -> Optional[list[Beatmap]]:
    if beatmaps := await set_from_database(set_id):
        return beatmaps

    if beatmaps := await set_from_api(set_id):
        return beatmaps


async def md5_from_database(md5: str) -> Optional[Beatmap]:
    map_collection = app.state.services.database.maps
    map_document = await map_collection.find_one({"md5": md5})

    if not map_document:
        return None

    # move into parse function perhaps?
    map_document["status"] = RankedStatus(int(map_document["status"]))
    map_document["mode"] = Mode(int(map_document["mode"]))
    map_document["last_update"] = datetime.fromisoformat(map_document["last_update"])
    map_document.pop("_id")

    return Beatmap(**map_document)


async def id_from_database(id: int) -> Optional[Beatmap]:
    map_collection = app.state.services.database.maps
    map_document = await map_collection.find_one({"id": id})

    if not map_document:
        return None

    # move into parse function perhaps?
    map_document["status"] = RankedStatus(int(map_document["status"]))
    map_document["mode"] = Mode(int(map_document["mode"]))
    map_document["last_update"] = datetime.fromisoformat(map_document["last_update"])
    map_document.pop("_id")

    return Beatmap(**map_document)


async def set_from_database(set_id: int) -> Optional[list[Beatmap]]:
    map_collection = app.state.services.database.maps
    map_documents = map_collection.find({"set_id": set_id})

    if not map_documents:
        return None

    maps = []
    async for map_document in map_documents:
        # move into parse function perhaps?
        map_document["status"] = RankedStatus(int(map_document["status"]))
        map_document["mode"] = Mode(int(map_document["mode"]))
        map_document["last_update"] = datetime.fromisoformat(
            map_document["last_update"],
        )
        map_document.pop("_id")

        maps.append(Beatmap(**map_document))

    return maps


GET_BEATMAP_URL = "https://old.ppy.sh/api/get_beatmaps"


async def save_to_database(beatmap: Beatmap) -> None:
    map_collection = app.state.services.database.maps
    await map_collection.update_one(
        {"md5": beatmap.md5},
        {"$set": beatmap.dict()},
        upsert=True,
    )


async def md5_from_api(md5: str) -> Optional[Beatmap]:
    async with ClientSession() as session:
        async with session.get(
            GET_BEATMAP_URL,
            params={"k": str(app.config.OSU_API_KEY), "h": md5},
        ) as response:
            if not response or response.status != status.HTTP_200_OK:
                return None

            response_json = await response.json()
            if not response_json:
                return None

    beatmaps = parse_from_osu_api(response_json)

    for beatmap in beatmaps:
        await save_to_database(beatmap)

    for beatmap in beatmaps:
        if beatmap.md5 == md5:
            return beatmap


async def id_from_api(id: int) -> Optional[Beatmap]:
    async with ClientSession() as session:
        async with session.get(
            GET_BEATMAP_URL,
            params={"k": str(app.config.OSU_API_KEY), "b": id},
        ) as response:
            if not response or response.status != status.HTTP_200_OK:
                return None

            response_json = await response.json()
            if not response_json:
                return None

    beatmaps = parse_from_osu_api(response_json)

    for beatmap in beatmaps:
        await save_to_database(beatmap)

    for beatmap in beatmaps:
        if beatmap.id == id:
            return beatmap


async def set_from_api(set_id: int) -> Optional[list[Beatmap]]:
    async with ClientSession() as session:
        async with session.get(
            GET_BEATMAP_URL,
            params={"k": str(app.config.OSU_API_KEY), "s": set_id},
        ) as response:
            if not response or response.status != status.HTTP_200_OK:
                return None

            response_json = await response.json()
            if not response_json:
                return None

    beatmaps = parse_from_osu_api(response_json)

    for beatmap in beatmaps:
        await save_to_database(beatmap)
    return beatmaps


IGNORED_BEATMAP_CHARS = dict.fromkeys(map(ord, r':\/*<>?"|'), None)

FROZEN_STATUSES = (RankedStatus.RANKED, RankedStatus.APPROVED, RankedStatus.LOVED)


def parse_from_osu_api(
    response_json_list: list[dict[str, Any]],
    frozen: bool = False,
) -> list[Beatmap]:
    maps = []

    for response_json in response_json_list:
        md5 = response_json["file_md5"]
        id = int(response_json["beatmap_id"])
        set_id = int(response_json["beatmapset_id"])

        artist, title, version, creator = (
            response_json["artist"],
            response_json["title"],
            response_json["version"],
            response_json["creator"],
        )

        filename = (
            ("{artist} - {title} ({creator}) [{version}].osu")
            .format(**response_json)
            .translate(IGNORED_BEATMAP_CHARS)
        )

        last_update_string = response_json["last_update"]
        last_update = datetime(
            year=int(last_update_string[0:4]),
            month=int(last_update_string[5:7]),
            day=int(last_update_string[8:10]),
            hour=int(last_update_string[11:13]),
            minute=int(last_update_string[14:16]),
            second=int(last_update_string[17:19]),
        )

        total_length = int(response_json["total_length"])

        if _max_combo := response_json.get("max_combo"):
            max_combo = int(_max_combo)
        else:
            max_combo = 0

        ranked_status = RankedStatus.from_osu_api(int(response_json["approved"]))
        if ranked_status in FROZEN_STATUSES:
            frozen = True  # beatmaps are always frozen when ranked/approved/loved

        mode = Mode(int(response_json["mode"]))

        if _bpm := response_json.get("bpm"):
            bpm = float(_bpm)
        else:
            bpm = 0.0

        cs = float(response_json["diff_size"])
        od = float(response_json["diff_overall"])
        ar = float(response_json["diff_approach"])
        hp = float(response_json["diff_drain"])
        diff = float(response_json["difficultyrating"])

        maps.append(
            Beatmap(
                md5,
                id,
                set_id,
                artist,
                title,
                version,
                creator,
                total_length,
                ranked_status,
                0,  # plays
                0,  # passes
                mode,
                cs,
                od,
                ar,
                hp,
                diff,
                last_update,
                max_combo,
                bpm,
                filename,
                frozen,
            ),
        )

    return maps


async def get_rating(beatmap: Beatmap) -> float:
    if beatmap.rating is not None:
        return beatmap.rating

    ratings_collection = app.state.services.database.ratings
    ratings = [
        document["rating"]
        async for document in ratings_collection.find({"map_md5": beatmap.md5})
    ]

    if ratings:
        rating = sum(ratings) / len(ratings)
    else:
        rating = 0.0

    beatmap.rating = rating
    return rating
