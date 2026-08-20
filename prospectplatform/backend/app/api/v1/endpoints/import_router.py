from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import tempfile
import os

from app.core.database import get_db
from app.collectors.csv_collector import CSVCollector

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/csv")
def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Arquivo deve ser um .csv")

    tmp_path = None
    try:
        content = file.file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="wb") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        collector = CSVCollector(db)
        stats = collector.import_csv(tmp_path)
        collector.commit()

        return {
            "message": "Importação concluída",
            "stats": stats,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na importação: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
