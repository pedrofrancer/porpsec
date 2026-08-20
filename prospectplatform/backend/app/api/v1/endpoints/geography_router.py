from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.geography import Country, Region, State, City, Neighborhood
from app.schemas.geography import (
    CountryRead, CountryFull, RegionRead, StateRead, CityRead, CityWithNeighborhoods,
)

router = APIRouter(prefix="/geography", tags=["geography"])


@router.get("/countries", response_model=list[CountryRead])
def list_countries(db: Session = Depends(get_db)):
    return db.query(Country).all()


@router.get("/countries/{country_id}", response_model=CountryFull)
def get_country_full(country_id: int, db: Session = Depends(get_db)):
    country = db.query(Country).filter(Country.id == country_id).first()
    if not country:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="País não encontrado")
    return country


@router.get("/states", response_model=list[StateRead])
def list_states(country_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(State)
    if country_id:
        query = query.filter(State.country_id == country_id)
    return query.all()


@router.get("/cities", response_model=list[CityRead])
def list_cities(state_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(City)
    if state_id:
        query = query.filter(City.state_id == state_id)
    return query.all()


@router.get("/neighborhoods")
def list_neighborhoods(city_id: int, db: Session = Depends(get_db)):
    return db.query(Neighborhood).filter(Neighborhood.city_id == city_id).all()
