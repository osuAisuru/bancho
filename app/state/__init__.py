from __future__ import annotations

import asyncio

import log
from . import cache
from . import services
from . import sessions
from app.typing import PacketHandler
from app.typing import PubsubHandler

PACKETS: dict[int, PacketHandler] = {}
RESTRICTED_PACKETS: dict[int, PacketHandler] = {}

PUBSUBS: dict[str, PubsubHandler] = {}

tasks: set[asyncio.Task] = set()


async def cancel_tasks() -> None:
    log.info(f"Cancelling {len(tasks)} tasks.")

    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)

    loop = asyncio.get_running_loop()
    for task in tasks:
        if not task.cancelled():
            if exception := task.exception():
                loop.call_exception_handler(
                    {
                        "message": "unhandled exception during loop shutdown",
                        "exception": exception,
                        "task": task,
                    },
                )
