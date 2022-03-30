from __future__ import annotations

import app.state
from app.constants.mode import Mode
from app.models import DBStats
from app.objects.stats import Stats


async def fetch(user_id: int, country: str, mode: Mode) -> Stats:
    stats_collection = app.state.services.database.ustats
    stats = await stats_collection.find_one({"user_id": user_id, "mode": mode})

    db_stats = DBStats(**stats)

    global_rank = await app.state.services.redis.zrevrank(
        f"aisuru:leaderboard:{int(mode)}",
        user_id,
    )
    if global_rank is not None:
        global_rank += 1
    else:
        global_rank = 0

    country_rank = await app.state.services.redis.zrevrank(
        f"aisuru:leaderboard:{int(mode)}:{country}",
        user_id,
    )
    if country_rank is not None:
        country_rank += 1
    else:
        country_rank = 0

    return Stats(
        global_rank=global_rank,
        country_rank=country_rank,
        **db_stats.dict(),
    )
