from __future__ import annotations

import asyncio

import bcrypt

cache: dict[str, str] = {}


async def verify_password(plain_password: bytes, hashed_password: str) -> bool:
    if hashed_password in cache:
        return cache[hashed_password] == plain_password

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        bcrypt.checkpw,
        plain_password,
        hashed_password.encode(),
    )

    if result:
        cache[hashed_password] = plain_password

    return result
