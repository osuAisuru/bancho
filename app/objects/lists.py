from __future__ import annotations

import asyncio
from typing import Iterable
from typing import Iterator
from typing import Optional
from typing import overload
from typing import TYPE_CHECKING
from typing import Union

from app.constants.privileges import Privileges

if TYPE_CHECKING:
    from app.objects.channel import Channel
    from app.objects.match import Match
    from app.objects.user import User

import log


class UserList(list["User"]):
    def __init__(self, *args, **kwargs):
        self.lock = asyncio.Lock()
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
        return [user for user in self if user.privileges & Privileges.STAFF]

    @property
    def restricted(self) -> list[User]:
        return [user for user in self if user.privileges & Privileges.RESTRICTED]

    @property
    def unrestricted(self) -> list[User]:
        return [user for user in self if not user.privileges & Privileges.RESTRICTED]

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
            return o in (chan.real_name for chan in self)
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
            if channel.real_name == name:
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


class MatchList(list["Match"]):
    def __init__(self) -> None:
        super().__init__([None] * 64)

    def __iter__(self) -> Iterator[Optional[Match]]:
        return super().__iter__()

    def __repr__(self) -> str:
        return f"[{', '.join(match.name for match in self if match)}]"

    def get_free(self) -> Optional[int]:
        for idx, match in enumerate(self):
            if match is None:
                return idx

    def append(self, match: Match) -> bool:
        if (free_idx := self.get_free()) is not None:
            match.id = free_idx
            self[free_idx] = match

            log.debug(f"{match} added to matches list.")
            return True

        log.warning(f"Tried to add {match} to matches list, but it is full.")
        return False

    def remove(self, match: Match) -> None:
        for idx, m in enumerate(self):
            if m == match:
                self[idx] = None
                log.debug(f"{match} removed from matches list.")

                break
