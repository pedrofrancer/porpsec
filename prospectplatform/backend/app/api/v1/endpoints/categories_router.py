from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.category import Category, Subcategory
from app.schemas.category import CategoryWithSubs, CategoryRead, SubcategoryRead

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/", response_model=list[CategoryWithSubs])
def list_categories(db: Session = Depends(get_db)):
    return db.query(Category).filter(Category.is_active == True).all()


@router.get("/{category_id}", response_model=CategoryWithSubs)
def get_category(category_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    return cat
