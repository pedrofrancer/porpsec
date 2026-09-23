"""site_previews: previa de site e follow-up da primeira resposta

Revision ID: a1e0c0de0004
Revises: a1e0c0de0003
Create Date: 2026-09-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1e0c0de0004'
down_revision: Union[str, None] = 'a1e0c0de0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'site_previews',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('reply_id', sa.Integer(), sa.ForeignKey('inbound_replies.id'), nullable=True, unique=True),
        sa.Column('slug', sa.String(length=120), nullable=False, unique=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pendente'),
        sa.Column('template_slug', sa.String(length=50), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('brand_kit_json', sa.Text(), nullable=True),
        sa.Column('html', sa.Text(), nullable=True),
        sa.Column('preview_url', sa.String(length=500), nullable=True),
        sa.Column('followup_subject', sa.String(length=300), nullable=True),
        sa.Column('followup_text', sa.Text(), nullable=True),
        sa.Column('followup_message_id', sa.Integer(), sa.ForeignKey('messages.id'), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_site_previews_company_id', 'site_previews', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_site_previews_company_id', table_name='site_previews')
    op.drop_table('site_previews')
