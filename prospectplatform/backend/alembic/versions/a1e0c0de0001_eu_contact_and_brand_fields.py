"""eu: e-mail/canal na company, contato e identidade visual no audit

Revision ID: a1e0c0de0001
Revises: c5254553fe9a
Create Date: 2026-09-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1e0c0de0001'
down_revision: Union[str, None] = 'c5254553fe9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=254), nullable=True))
        batch_op.add_column(sa.Column('email_source', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('preferred_channel', sa.String(length=20), nullable=True))

    with op.batch_alter_table('audits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('site_lang', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('emails_found', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('legal_entity_signal', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('logo_url', sa.String(length=1000), nullable=True))
        batch_op.add_column(sa.Column('dominant_colors', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('og_image_url', sa.String(length=1000), nullable=True))
        batch_op.add_column(sa.Column('about_snippet', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('audits', schema=None) as batch_op:
        for col in ('about_snippet', 'og_image_url', 'dominant_colors', 'logo_url',
                    'legal_entity_signal', 'emails_found', 'site_lang'):
            batch_op.drop_column(col)

    with op.batch_alter_table('companies', schema=None) as batch_op:
        for col in ('preferred_channel', 'email_source', 'email'):
            batch_op.drop_column(col)
