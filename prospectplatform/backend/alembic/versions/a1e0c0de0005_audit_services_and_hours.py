"""audit services and opening hours (collected from site JSON-LD)

Revision ID: a1e0c0de0005
Revises: a1e0c0de0004
Create Date: 2026-09-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1e0c0de0005'
down_revision: Union[str, None] = 'a1e0c0de0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('audits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('services_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('opening_hours_json', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('audits', schema=None) as batch_op:
        batch_op.drop_column('opening_hours_json')
        batch_op.drop_column('services_json')
