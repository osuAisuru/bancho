from __future__ import annotations

import bcrypt

cache: dict[str, str] = {}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password in cache:
        return cache[hashed_password] == plain_password

    result = bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    if result:
        cache[hashed_password] = plain_password

    return result
