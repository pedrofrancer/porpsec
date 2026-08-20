import os
import sys
from pathlib import Path

_backend = str(Path(__file__).resolve().parent.parent / "backend")
os.chdir(_backend)
sys.path.insert(0, _backend)

from app.core.database import SessionLocal, create_tables
from app.models.geography import Country, Region, State, City, Neighborhood


GEOGRAPHY_DATA = {
    "Brasil": {
        "code": "BR",
        "regions": {
            "Sudeste": {
                "states": {
                    "Rio de Janeiro": {
                        "code": "RJ",
                        "cities": {
                            "Região dos Lagos": [
                                "Araruama",
                                "Armação dos Búzios",
                                "Arraial do Cabo",
                                "Cabo Frio",
                                "Iguaba Grande",
                                "São Pedro da Aldeia",
                                "Saquarema",
                            ]
                        }
                    }
                }
            }
        }
    }
}


def seed_geography():
    create_tables()
    db = SessionLocal()
    try:
        for country_name, country_data in GEOGRAPHY_DATA.items():
            country = db.query(Country).filter(Country.name == country_name).first()
            if not country:
                country = Country(name=country_name, code=country_data["code"])
                db.add(country)
                db.flush()

            for region_name, region_data in country_data.get("regions", {}).items():
                region = db.query(Region).filter(
                    Region.country_id == country.id, Region.name == region_name
                ).first()
                if not region:
                    region = Region(country_id=country.id, name=region_name)
                    db.add(region)
                    db.flush()

                for state_name, state_data in region_data.get("states", {}).items():
                    state = db.query(State).filter(
                        State.country_id == country.id, State.code == state_data["code"]
                    ).first()
                    if not state:
                        state = State(
                            country_id=country.id, region_id=region.id,
                            name=state_name, code=state_data["code"],
                        )
                        db.add(state)
                        db.flush()

                    for region_label, cities in state_data.get("cities", {}).items():
                        for city_name in cities:
                            city = db.query(City).filter(
                                City.state_id == state.id, City.name == city_name
                            ).first()
                            if not city:
                                city = City(state_id=state.id, name=city_name)
                                db.add(city)
                                db.flush()

        db.commit()
        print("Geografia seed concluído com sucesso!")
    except Exception as e:
        db.rollback()
        print(f"Erro no seed de geografia: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_geography()
