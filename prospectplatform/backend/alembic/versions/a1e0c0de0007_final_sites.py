"""final_sites: o site pronto pra empresa fechar (sem faixa de previa, indexavel, sem prazo)

Revision ID: a1e0c0de0007
Revises: a1e0c0de0006
Create Date: 2026-09-24 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1e0c0de0007'
down_revision: Union[str, None] = 'a1e0c0de0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'final_sites',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False, unique=True),
        sa.Column('slug', sa.String(length=120), nullable=False, unique=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='publicado'),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('html', sa.Text(), nullable=True),
        sa.Column('public_url', sa.String(length=500), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_final_sites_company_id', 'final_sites', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_final_sites_company_id', table_name='final_sites')
    op.drop_table('final_sites')
