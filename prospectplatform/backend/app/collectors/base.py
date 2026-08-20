from abc import ABC, abstractmethod
from sqlalchemy.orm import Session


class BaseCollector(ABC):
    """Interface base para todos os coletores de dados."""

    def __init__(self, db: Session):
        self.db = db
        self.stats = {
            "total": 0,
            "imported": 0,
            "skipped_duplicates": 0,
            "errors": 0,
        }

    @abstractmethod
    def collect(self, **kwargs) -> dict:
        """Executa a coleta. Retorna dict com estatísticas."""
        ...

    def commit(self):
        self.db.commit()

    def reset_stats(self):
        self.stats = {
            "total": 0,
            "imported": 0,
            "skipped_duplicates": 0,
            "errors": 0,
        }
