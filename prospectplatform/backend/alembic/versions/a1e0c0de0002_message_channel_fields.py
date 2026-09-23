"""mensagem: canal, tipo, assunto, idioma e thread

Revision ID: a1e0c0de0002
Revises: a1e0c0de0001
Create Date: 2026-09-22 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1e0c0de0002'
down_revision: Union[str, None] = 'a1e0c0de0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('channel', sa.String(length=20), nullable=False, server_default='whatsapp'))
        batch_op.add_column(sa.Column('message_type', sa.String(length=30), nullable=False, server_default='outreach'))
        batch_op.add_column(sa.Column('subject', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('language', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('thread_id', sa.String(length=300), nullable=True))
        batch_op.create_index('ix_messages_thread_id', ['thread_id'])


def downgrade() -> None:
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_index('ix_messages_thread_id')
        for col in ('thread_id', 'language', 'subject', 'message_type', 'channel'):
            batch_op.drop_column(col)
