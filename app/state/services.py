from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aioredis
from geoip2 import database as geoloc_database
from motor.motor_asyncio import AsyncIOMotorClient

import app.config
import app.state
from app.constants.countries import OSU_GEOLOC

client = AsyncIOMotorClient(str(app.config.MONGODB_DSN))
database = client.aisuru

redis: aioredis.Redis = aioredis.from_url(str(app.config.REDIS_DSN))
geoloc = geoloc_database.Reader("ext/geoloc.mmdb")


@dataclass
class Country:
    code: int
    acronym: str

    @classmethod
    def from_iso(cls, acronym: str) -> Country:
        code = OSU_GEOLOC[acronym]

        return Country(code, acronym)


class Geolocation:
    def __init__(
        self,
        long: float = 0.0,
        lat: float = 0.0,
        country: Country = Country(0, "xx"),
        ip: str = "",
    ) -> None:
        self.long = long
        self.lat = lat
        self.country = country

        self.ip = ip

    @classmethod
    def from_ip(self, headers: dict[str, Any]) -> Geolocation:
        if not (ip := headers.get("CF-Connecting-IP")):
            forwards = headers["X-Forwarded-For"].split(",")

            if len(forwards) != 1:
                ip = forwards[0]
            else:
                ip = headers["X-Real-IP"]

        if not (geoloc := app.state.cache.geoloc.get(ip)):
            city = app.state.services.geoloc.city(ip)

            iso_code = city.country.iso_code.lower()
            country = Country.from_iso(iso_code)

            geoloc = Geolocation(
                city.location.longitude,
                city.location.latitude,
                country,
                ip,
            )

            app.state.cache.geoloc[ip] = geoloc

        return geoloc
