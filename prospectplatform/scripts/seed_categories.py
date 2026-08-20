import os
import sys
from pathlib import Path

_backend = str(Path(__file__).resolve().parent.parent / "backend")
os.chdir(_backend)
sys.path.insert(0, _backend)

from app.core.database import SessionLocal, create_tables
from app.models.category import Category, Subcategory


CATEGORIES_DATA = [
    {
        "name": "Barbearia",
        "slug": "barbearia",
        "subcategories": ["Barbeiro", "Barbearia premium"],
    },
    {
        "name": "Salão de Beleza",
        "slug": "salao-de-beleza",
        "subcategories": ["Cabelo", "Manicure/Pedicure", "Maquiagem", "Estética"],
    },
    {
        "name": "Clínica",
        "slug": "clinica",
        "subcategories": ["Estética", "Odontológica", "Dermatologia", "Fisioterapia"],
    },
    {
        "name": "Restaurante",
        "slug": "restaurante",
        "subcategories": ["Comida caseira", "Fast food", "Pizzaria", "Churrascaria", "Marisqueira"],
    },
    {
        "name": "Academia",
        "slug": "academia",
        "subcategories": ["Musculação", "Crossfit", "Yoga/Pilates", "Artes marciais"],
    },
    {
        "name": "Pousada",
        "slug": "pousada",
        "subcategories": ["Pousada", "Hotel", "Hostel"],
    },
    {
        "name": "Imobiliária",
        "slug": "imobiliaria",
        "subcategories": ["Venda", "Aluguel", "Lançamento"],
    },
    {
        "name": "Oficina",
        "slug": "oficina",
        "subcategories": ["Mecânica", "Elétrica", "Funilaria", "Serralheria"],
    },
]


def seed_categories():
    create_tables()
    db = SessionLocal()
    try:
        for cat_data in CATEGORIES_DATA:
            cat = db.query(Category).filter(Category.slug == cat_data["slug"]).first()
            if not cat:
                cat = Category(name=cat_data["name"], slug=cat_data["slug"])
                db.add(cat)
                db.flush()

            for sub_name in cat_data["subcategories"]:
                sub_slug = sub_name.lower().replace(" ", "-").replace("/", "-")
                existing = db.query(Subcategory).filter(
                    Subcategory.category_id == cat.id,
                    Subcategory.slug == sub_slug,
                ).first()
                if not existing:
                    sub = Subcategory(
                        category_id=cat.id, name=sub_name, slug=sub_slug,
                    )
                    db.add(sub)

        db.commit()
        print("Categorias seed concluído com sucesso!")
    except Exception as e:
        db.rollback()
        print(f"Erro no seed de categorias: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_categories()
