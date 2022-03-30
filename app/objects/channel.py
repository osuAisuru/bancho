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
        privileges: Privileges = Privileges.NORMAL,
        auto_join: bool = True,
        instance: bool = False,
        real_name: str = None,
    ) -> None:
        self.real_name = real_name or name
        self.name = name
        self.topic = topic
        self.privileges = privileges
        self.auto_join = auto_join
        self.instance = instance

        self.users: list[User] = []

    def __repr__(self) -> str:
        return f"<{self.name}>"

    @property
    def user_count(self) -> int:
        return len(self.users)

    def __contains__(self, user: User) -> bool:
        return user in self.users

    def has_permission(self, privileges: Privileges) -> bool:
        if not self.privileges:
            return True

        return privileges & self.privileges != 0

    def add_user(self, user: User) -> None:
        if user in self:
            return  # ?

        self.users.append(user)

    def remove_user(self, user: User) -> None:
        if user not in self:
            return  # ?

        self.users.remove(user)

    def send(self, msg: str, sender: User, to_self: bool = False) -> None:
        if not self.has_permission(sender.privileges):
            return

        self.selective_send(msg, sender, self.users)

    def selective_send(
        self,
        msg: str,
        sender: User,
        recipients: list[User],
    ) -> None:
        if not self.has_permission(sender.privileges):
            return

        for user in recipients:
            if user not in self:
                continue

            user.receive_message(msg, sender)

    def enqueue(self, data: bytes, immune: list[int] = []) -> None:
        for user in self.users:
            if user.id in immune:
                continue

            user.enqueue(data)
