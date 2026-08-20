import csv
import sys
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.geography import City
from app.models.category import Category


class CSVCollector:
    REQUIRED_FIELDS = {"nome", "categoria", "cidade"}

    def __init__(self, db: Session):
        self.db = db
        self.stats = {"total": 0, "imported": 0, "skipped_duplicates": 0, "errors": 0}

    def import_csv(self, file_path: str) -> dict:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = set(reader.fieldnames or [])
            missing = self.REQUIRED_FIELDS - headers
            if missing:
                raise ValueError(f"Campos obrigatórios ausentes no CSV: {missing}")

            for row in reader:
                self.stats["total"] += 1
                try:
                    self._process_row(row)
                except Exception as e:
                    self.stats["errors"] += 1
                    print(f"Erro na linha {self.stats['total']}: {e}")

        return self.stats

    def _process_row(self, row: dict):
        nome = row.get("nome", "").strip()
        categoria_slug = row.get("categoria", "").strip().lower().replace(" ", "-")
        cidade_nome = row.get("cidade", "").strip()
        telefone = row.get("telefone", "").strip() or None
        website = row.get("website", "").strip() or None
        instagram = row.get("instagram", "").strip() or None

        if not nome or not categoria_slug or not cidade_nome:
            raise ValueError("nome, categoria e cidade são obrigatórios")

        city = self.db.query(City).filter(City.name == cidade_nome).first()
        if not city:
            raise ValueError(
                f"Cidade '{cidade_nome}' não encontrada. Execute seed_geography.py primeiro."
            )

        category = self.db.query(Category).filter(Category.slug == categoria_slug).first()
        if not category:
            raise ValueError(
                f"Categoria '{categoria_slug}' não encontrada. Execute seed_categories.py primeiro."
            )

        if telefone:
            existing = self.db.query(Company).filter(Company.phone == telefone).first()
            if existing:
                self.stats["skipped_duplicates"] += 1
                return

        if website:
            existing = self.db.query(Company).filter(Company.website == website).first()
            if existing:
                self.stats["skipped_duplicates"] += 1
                return

        company = Company(
            name=nome,
            city_id=city.id,
            category_id=category.id,
            phone=telefone,
            website=website,
            instagram=instagram,
            source="csv_import",
            collected_at=datetime.now(timezone.utc),
        )
        self.db.add(company)
        self.db.flush()
        self.stats["imported"] += 1

    def commit(self):
        self.db.commit()
