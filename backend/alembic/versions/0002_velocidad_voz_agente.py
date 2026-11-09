"""velocidad de la voz por agente IA

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('tb_agente_ia', schema=None) as batch_op:
        batch_op.add_column(sa.Column('velocidad_voz', sa.Numeric(precision=3, scale=2), nullable=False,
                                      server_default='1.00'))


def downgrade() -> None:
    with op.batch_alter_table('tb_agente_ia', schema=None) as batch_op:
        batch_op.drop_column('velocidad_voz')
