from __future__ import annotations

from fastapi import APIRouter
from fastapi import Query

import app.config
import app.usecases

router = APIRouter(tags=["Aisuru Bancho API"])


@router.get("/user-auth")
async def check_user_credentials(
    name: str = Query(...),
    password_md5: str = Query(..., alias="password"),
    api_key: str = Query(..., alias="key"),
):
    if api_key != app.config.API_SECRET:
        return {"status": "error", "message": "Invalid API key"}

    if not (user := app.usecases.user.cache_fetch(name=name)):
        return {"status": "error", "message": "User not found"}

    if user.password_md5 != password_md5:
        return {"status": "error", "message": "Invalid password"}

    return {"status": "ok", "user": user.basic_info}
