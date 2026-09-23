"""inbound_replies: respostas recebidas aos outreaches

Revision ID: a1e0c0de0003
Revises: a1e0c0de0002
Create Date: 2026-09-22 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1e0c0de0003'
down_revision: Union[str, None] = 'a1e0c0de0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'inbound_replies',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('message_id', sa.Integer(), sa.ForeignKey('messages.id'), nullable=True),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('external_id', sa.String(length=300), nullable=False, unique=True),
        sa.Column('from_address', sa.String(length=254), nullable=True),
        sa.Column('subject', sa.String(length=300), nullable=True),
        sa.Column('raw_content', sa.Text(), nullable=False, server_default=''),
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='reply'),
        sa.Column('is_first_reply', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('resulted_in_template', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_inbound_replies_company_id', 'inbound_replies', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_inbound_replies_company_id', table_name='inbound_replies')
    op.drop_table('inbound_replies')
