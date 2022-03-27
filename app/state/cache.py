from __future__ import annotations

from app.state.services import Geolocation

IPAddress = str
geoloc: dict[IPAddress, Geolocation] = {}
