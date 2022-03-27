from __future__ import annotations

from typing import TYPE_CHECKING

from app.constants.privileges import Privileges

if TYPE_CHECKING:
    from app.objects.user import User


class Channel:
    def __init__(
        self,
        name: str,
        topic: str,
        priv: Privileges = Privileges.NORMAL,
        auto_join: bool = True,
        instance: bool = False,
    ) -> None:
        self.name = name
        self.topic = topic
        self.priv = priv
        self.auto_join = auto_join
        self.instance = instance

        self.users: list[User] = []

    def __repr__(self) -> str:
        return f"<{self.name}>"

    @property
    def player_count(self) -> int:
        return len(self.players)

    def __contains__(self, user: User) -> bool:
        return user in self.users

    def has_permission(self, priv: Privileges) -> bool:
        if not self.priv:
            return True

        return priv & self.priv != 0

    def add_user(self, user: User) -> None:
        if user in self:
            return  # ?

        self.users.append(user)

    def remove_user(self, user: User) -> None:
        if user not in self:
            return  # ?

        self.users.remove(user)

    def send(self, msg: str, sender: User, to_self: bool = False) -> None:
        if not self.has_permission(sender.priv):
            return

        ...

    def selective_send(
        self,
        msg: str,
        sender: User,
        recipients: list[User],
    ) -> None:
        if not self.has_permission(sender.priv):
            return

        ...

    def enqueue(self, data: bytes, immune: list[int] = []) -> None:
        ...
