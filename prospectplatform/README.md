# ProspectPlatform

Plataforma de inteligência comercial B2B para prospecção de negócios locais.

## Setup

```bash
cd prospectplatform/backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env
```

## Inicializar banco e dados

```bash
cd prospectplatform/backend
python -c "from app.core.database import create_tables; create_tables()"
cd ../scripts
python seed_geography.py
python seed_categories.py
```

## Rodar

```bash
cd prospectplatform/backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Interface: http://localhost:8000
API Docs: http://localhost:8000/docs

## Importar CSV

```bash
# Endpoint via API
curl -X POST http://localhost:8000/api/v1/import/csv -F "file=@data/samples/sample_businesses.csv"
```

## Estrutura

- `backend/app/` — Código da aplicação
- `backend/app/models/` — Models SQLAlchemy
- `backend/app/schemas/` — Schemas Pydantic
- `backend/app/api/` — Endpoints FastAPI
- `backend/app/collectors/` — Coletores de dados (CSV, Google Maps)
- `backend/app/auditors/` — Auditores digitais
- `backend/app/ai/` — Providers de LLM
- `backend/app/opportunities/` — Engine de oportunidades
- `backend/app/prospecting/` — Fila, opt-out, compliance
- `config/` — Configurações (regras de oportunidades)
- `scripts/` — Seeds e scripts utilitários
- `interface/` — Interface HTML
- `data/samples/` — CSVs de exemplo
