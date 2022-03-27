from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.objects.user import User


class Clan:
    def __init__(
        self,
        id: int,
        name: str,
        tag: str,
        owner: int,
        members: list[int] = [],
    ) -> None:
        self.id = id
        self.name = name
        self.tag = tag
        self.owner = owner

        self.members = members

    def __repr__(self) -> str:
        return f"[{self.tag}] {self.name}"

    async def add_member(self, user: User) -> None:
        ...

    async def remove_member(self, user: User) -> None:
        ...

    async def get_members(self) -> None:
        ...
