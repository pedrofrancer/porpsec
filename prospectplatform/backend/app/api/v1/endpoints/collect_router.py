from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.collectors.google_maps import GoogleMapsCollector

router = APIRouter(prefix="/collect", tags=["collect"])


class GoogleMapsRequest(BaseModel):
    category_slug: str
    city_name: str
    max_results: int = 60
    headless: bool = True


@router.post("/google-maps")
def collect_google_maps(data: GoogleMapsRequest, db: Session = Depends(get_db)):
    try:
        collector = GoogleMapsCollector(db)
        stats = collector.collect(
            category_slug=data.category_slug,
            city_name=data.city_name,
            max_results=data.max_results,
            headless=data.headless,
        )
        collector.commit()
        return {"message": "Coleta concluída", "stats": stats}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na coleta: {str(e)}")
