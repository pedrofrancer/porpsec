from pydantic import BaseModel


class CategoryRead(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool

    model_config = {"from_attributes": True}


class SubcategoryRead(BaseModel):
    id: int
    category_id: int
    name: str
    slug: str

    model_config = {"from_attributes": True}


class CategoryWithSubs(CategoryRead):
    subcategories: list[SubcategoryRead] = []
