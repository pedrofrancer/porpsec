"""Teste ponta a ponta sem contatar empresa real.

Cria uma empresa de teste com o SEU e-mail, gera o outreach no idioma do pais escolhido e
envia pela caixa configurada no .env. Responda esse e-mail a partir do endereco de teste:
em ate ~1 minuto a resposta aparece na aba Respostas e a previa do site vira rascunho.

Uso (na pasta prospectplatform, com o servidor rodando em outro terminal):
    .venv\\Scripts\\python scripts\\teste_ponta_a_ponta.py --para voce@outro-email.com --pais FR
    .venv\\Scripts\\python scripts\\teste_ponta_a_ponta.py --para voce@x.com --pais NL --site https://site-real.nl

A politica de destinatario (dominio da empresa, B.V. na Holanda) e ignorada de proposito:
o destinatario e voce.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_backend = str(Path(__file__).resolve().parent.parent / "backend")
os.chdir(_backend)
sys.path.insert(0, _backend)

from app.core.config import settings  # noqa: E402
from app.core.countries import get_country  # noqa: E402
from app.core.database import SessionLocal, create_tables  # noqa: E402
from app.models.audit import Audit  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.geography import City, Country, State  # noqa: E402
from app.models.prospection import ProspectingQueue  # noqa: E402
from app.sending.dispatcher import Dispatcher  # noqa: E402

CITY_BY_COUNTRY = {"PT": "Lisboa", "BE": "Bruxelles", "FR": "Paris", "NL": "Amsterdam"}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--para", required=True, help="seu e-mail de teste (nao use o mesmo do .env)")
    parser.add_argument("--pais", default="FR", choices=sorted(CITY_BY_COUNTRY))
    parser.add_argument("--categoria", default="barbearia")
    parser.add_argument("--nome", default="Atelier Teste")
    parser.add_argument("--site", help="site real para auditar (cores, logo, idioma); opcional")
    args = parser.parse_args()

    if not settings.email_configured:
        sys.exit("Configure EMAIL_ADDRESS, EMAIL_APP_PASSWORD, SENDER_BRAND e SENDER_POSTAL_ADDRESS no backend/.env")
    if args.para.strip().lower() == settings.EMAIL_ADDRESS.lower():
        sys.exit("Use um endereco de teste diferente da caixa que envia, senao a resposta nao chega ao INBOX.")

    create_tables()
    db = SessionLocal()
    city = db.query(City).join(State).join(Country).filter(
        City.name == CITY_BY_COUNTRY[args.pais], Country.code == args.pais).first()
    category = db.query(Category).filter(Category.slug == args.categoria).first()
    if not city or not category:
        sys.exit("Rode antes: scripts/seed_geography.py e scripts/seed_categories.py")

    company = Company(name=args.nome, city_id=city.id, category_id=category.id, email=args.para.strip().lower(),
                      email_source="teste", website=args.site, preferred_channel="email",
                      address=f"{city.name}", source="teste", collected_at=datetime.now(timezone.utc))
    db.add(company)
    db.commit()

    dispatcher = Dispatcher(db)
    if args.site:
        audit, opportunities = await dispatcher._prepare_company(company)
    else:
        audit = Audit(company_id=company.id, digital_score=35, has_viewport=False, has_https=True,
                      has_scheduling=False, response_time_ms=4800, audited_at=datetime.now(timezone.utc))
        db.add(audit)
        db.commit()
        opportunities = []

    country = get_country(args.pais)
    msg, error = await dispatcher._compose(company, audit, opportunities, "email", country)
    if error:
        sys.exit(f"Mensagem recusada pela validacao: {error}\n\n{msg.message_text}")

    db.add(ProspectingQueue(company_id=company.id, status="TESTE", notes="teste ponta a ponta"))
    db.commit()
    sent = await dispatcher._send_message(msg, company)
    print(f"\nAssunto: {msg.subject}\n\n{msg.message_text}\n")
    print("ENVIADO. Responda esse e-mail a partir de", args.para if sent else "(falhou, veja o log acima)")
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
