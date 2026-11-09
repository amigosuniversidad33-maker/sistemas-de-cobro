"""tiempo de silencio máximo por agente (espera a que el cliente empiece a hablar)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-09 10:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('tb_agente_ia', schema=None) as batch_op:
        batch_op.add_column(sa.Column('silencio_max_seg', sa.Numeric(precision=3, scale=1), nullable=False,
                                      server_default='6.0'))


def downgrade() -> None:
    with op.batch_alter_table('tb_agente_ia', schema=None) as batch_op:
        batch_op.drop_column('silencio_max_seg')
