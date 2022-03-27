from __future__ import annotations

from app.constants.mode import Mode
from app.models import DBStats
from app.objects.stats import Stats
from app.state.services import database
from app.state.services import redis


async def fetch(user_id: int, country: str, mode: Mode) -> Stats:
    stats = database.find_one({"user_id": user_id, "mode": mode})

    db_stats = DBStats(**stats)

    global_rank = await redis.zrevrank(f"aisuru:leaderboard:{int(mode)}", user_id)
    if global_rank is not None:
        global_rank += 1

    country_rank = await redis.zrevrank(
        f"aisuru:leaderboard:{int(mode)}:{country}",
        user_id,
    )
    if country_rank is not None:
        country_rank += 1

    return Stats(
        global_rank,
        country_rank,
        **db_stats,
    )
