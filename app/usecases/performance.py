from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from aiohttp import ClientSession
from aisuru_pp_py import Calculator
from aisuru_pp_py import ScoreParams
from fastapi import status

from app.constants.mods import Mods
from app.objects.beatmap import Beatmap


class ScoreParameters(TypedDict):
    mods: Mods
    acc: float
    nmiss: int
    max_combo: int


@dataclass
class ScoreResult:
    pp: float
    sr: float

    ar: float
    cs: float
    od: float
    bpm: float


DATA_PATH = Path("/home/james/aisuru/web/data")
BEATMAPS_PATH = DATA_PATH / "beatmaps"


def calculate_score(_score_params: ScoreParameters, osu_file_path: Path) -> ScoreResult:
    calculator = Calculator(str(osu_file_path))

    score_params = ScoreParams(
        mods=_score_params["mods"].value,
        acc=_score_params["acc"],
        nMisses=_score_params["nmiss"],
        combo=_score_params["max_combo"],
    )

    (result,) = calculator.calculate(score_params)

    return ScoreResult(
        pp=round(result.pp, 2),
        sr=round(result.stars, 2),
        ar=round(result.ar, 2),
        cs=round(result.cs, 2),
        od=round(result.od, 2),
        bpm=round(result.bpm, 2),
    )


async def check_local_file(osu_file_path: Path, map_id: int, map_md5: str) -> bool:
    if (
        not osu_file_path.exists()
        or hashlib.md5(osu_file_path.read_bytes()).hexdigest() != map_md5
    ):
        async with ClientSession() as session:
            async with session.get(f"https://old.ppy.sh/osu/{map_id}") as response:
                if response.status != status.HTTP_200_OK:
                    return False

                osu_file_path.write_bytes(await response.read())

    return True


async def np_msg(bmap: Beatmap, mods: Mods) -> str:
    pp_results: dict[float, ScoreResult] = {}
    for acc in (95.0, 97.0, 98.0, 99.0, 100.0):
        params = ScoreParameters(
            mods=mods,
            acc=acc,
            nmiss=0,
            max_combo=bmap.max_combo,
        )

        osu_file_path = BEATMAPS_PATH / f"{bmap.id}.osu"
        if not await check_local_file(osu_file_path, bmap.id, bmap.md5):
            return "Something went wrong"

        pp_results[acc] = calculate_score(params, osu_file_path)

    mod_str = " "
    if mods > Mods.NOMOD:
        mod_str += f"+{mods!r}"

    return (
        f"{bmap.embed}{mod_str} // 95%: {pp_results[95.0].pp}pp | 97%: {pp_results[97.0].pp}pp | 98%: {pp_results[98.0].pp}pp | "
        f"99%: {pp_results[99.0].pp}pp | 100%: {pp_results[100.0].pp}pp "
        f"// {pp_results[95.0].sr}★ | {pp_results[95.0].bpm:.0f}BPM | CS {pp_results[95.0].cs}, AR {pp_results[95.0].ar}, OD {pp_results[95.0].od}"
    )
