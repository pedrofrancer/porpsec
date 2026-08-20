from pydantic import BaseModel
from datetime import datetime


class CountryRead(BaseModel):
    id: int
    name: str
    code: str

    model_config = {"from_attributes": True}


class RegionRead(BaseModel):
    id: int
    country_id: int
    name: str

    model_config = {"from_attributes": True}


class StateRead(BaseModel):
    id: int
    country_id: int
    region_id: int | None
    name: str
    code: str

    model_config = {"from_attributes": True}


class CityRead(BaseModel):
    id: int
    state_id: int
    name: str

    model_config = {"from_attributes": True}


class NeighborhoodRead(BaseModel):
    id: int
    city_id: int
    name: str

    model_config = {"from_attributes": True}


class CityWithNeighborhoods(CityRead):
    neighborhoods: list[NeighborhoodRead] = []


class StateWithCities(StateRead):
    cities: list[CityWithNeighborhoods] = []


class RegionWithStates(RegionRead):
    states: list[StateWithCities] = []


class CountryFull(CountryRead):
    regions: list[RegionWithStates] = []
