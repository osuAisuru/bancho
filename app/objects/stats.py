from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Stats:
    total_score: int
    ranked_score: int

    accuracy: float
    pp: int

    max_combo: int
    total_hits: int

    playcount: int
    playtime: int

    global_rank: int
    country_rank: int
