from __future__ import annotations

from typing import Iterable
from typing import Iterator
from typing import Optional
from typing import overload
from typing import TYPE_CHECKING
from typing import Union

from app.constants.privileges import Privileges

if TYPE_CHECKING:
    from app.objects.channel import Channel
    from app.objects.user import User

import log


class UserList(list["User"]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __iter__(self) -> Iterator[User]:
        return super().__iter__()

    def __contains__(self, user: Union[User, str, int]) -> bool:
        if isinstance(user, str):
            return user in [name for name in self.names]
        elif isinstance(user, int):
            return user in [id for id in self.ids]
        else:
            return super().__contains__(user)

    def __repr__(self) -> str:
        return f"[{', '.join(map(repr, self))}]"

    @property
    def ids(self) -> list[int]:
        return [user.id for user in self]

    @property
    def names(self) -> list[str]:
        return [user.name for user in self]

    @property
    def staff(self) -> list[User]:
        return [user for user in self if user.priv & Privileges.STAFF]

    @property
    def restricted(self) -> list[User]:
        return [user for user in self if user.priv & Privileges.RESTRICTED]

    @property
    def unrestricted(self) -> list[User]:
        return [user for user in self if not user.priv & Privileges.RESTRICTED]

    def enqueue(self, data: bytes, immune: list[int] = []) -> None:
        for user in self:
            if user.id not in immune:
                user.enqueue(data)

    def append(self, user: User) -> None:
        if user in self:
            return

        super().append(user)

    def remove(self, user: User) -> None:
        if user not in self:
            return

        super().remove(user)


class ChannelList(list["Channel"]):
    def __iter__(self) -> Iterator[Channel]:
        return super().__iter__()

    def __contains__(self, o: Union[Channel, str]) -> bool:
        if isinstance(o, str):
            return o in (chan.name for chan in self)
        else:
            return super().__contains__(o)

    @overload
    def __getitem__(self, index: int) -> Channel:
        ...

    @overload
    def __getitem__(self, index: str) -> Channel:
        ...

    @overload
    def __getitem__(self, index: slice) -> list[Channel]:
        ...

    def __getitem__(
        self,
        index: Union[int, slice, str],
    ) -> Union[Channel, list[Channel]]:
        if isinstance(index, str):
            return self.get_by_name(index)
        else:
            return super().__getitem__(index)

    def get_by_name(self, name: str) -> Optional[Channel]:
        for channel in self:
            if channel.name == name:
                return channel

    def append(self, channel: Channel) -> None:
        super().append(channel)

        log.debug(f"{channel} added to channels list.")

    def extend(self, channels: Iterable[Channel]) -> None:
        super().extend(channels)

        log.debug(f"{channels} added to channels list.")

    def remove(self, channel: Channel) -> None:
        super().remove(channel)

        log.debug(f"{channel} removed from channels list.")
