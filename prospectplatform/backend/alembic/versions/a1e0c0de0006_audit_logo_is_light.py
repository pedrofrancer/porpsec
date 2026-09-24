"""audit logo_is_light (logo claro precisa de fundo escuro por cima)

Revision ID: a1e0c0de0006
Revises: a1e0c0de0005
Create Date: 2026-09-24 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1e0c0de0006'
down_revision: Union[str, None] = 'a1e0c0de0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('audits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('logo_is_light', sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('audits', schema=None) as batch_op:
        batch_op.drop_column('logo_is_light')
