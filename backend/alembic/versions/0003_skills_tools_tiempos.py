"""skills por agente y supervisor, tools editables por agente, tiempos de llamada, preguntas frecuentes

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('tb_agente_ia', schema=None) as batch_op:
        batch_op.add_column(sa.Column('herramientas', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('espera_inicio_seg', sa.Numeric(precision=3, scale=1), nullable=False,
                                      server_default='0.0'))
        batch_op.add_column(sa.Column('silencio_fin_seg', sa.Numeric(precision=3, scale=1), nullable=False,
                                      server_default='2.0'))
    op.create_table('tb_skill',
    sa.Column('id_skill', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('ambito', sa.String(length=15), nullable=False),
    sa.Column('cuando_usar', sa.String(length=255), nullable=False),
    sa.Column('contenido', sa.Text(), nullable=False),
    sa.Column('autor', sa.String(length=120), nullable=False),
    sa.Column('estado', sa.String(length=15), nullable=False),
    sa.Column('id_usuario', sa.Integer(), nullable=True),
    sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['id_usuario'], ['tb_usuario.id_usuario'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id_skill'),
    sa.UniqueConstraint('nombre', 'version', name='uq_skill_version')
    )
    op.create_table('tb_agente_skill',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('id_agente', sa.Integer(), nullable=False),
    sa.Column('id_skill', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id_agente'], ['tb_agente_ia.id_agente'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['id_skill'], ['tb_skill.id_skill'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id_agente', 'id_skill', name='uq_agente_skill')
    )
    op.create_table('tb_herramienta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=60), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('descripcion', sa.String(length=1000), nullable=False),
    sa.Column('texto_respuesta', sa.String(length=1000), nullable=True),
    sa.Column('id_usuario', sa.Integer(), nullable=True),
    sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['id_usuario'], ['tb_usuario.id_usuario'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre', 'version', name='uq_herramienta_version')
    )
    op.create_table('tb_pregunta_frecuente',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pregunta', sa.String(length=255), nullable=False),
    sa.Column('palabras_clave', sa.String(length=255), nullable=False),
    sa.Column('respuesta', sa.String(length=1000), nullable=False),
    sa.Column('activa', sa.Boolean(), nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('tb_pregunta_frecuente')
    op.drop_table('tb_herramienta')
    op.drop_table('tb_agente_skill')
    op.drop_table('tb_skill')
    with op.batch_alter_table('tb_agente_ia', schema=None) as batch_op:
        batch_op.drop_column('silencio_fin_seg')
        batch_op.drop_column('espera_inicio_seg')
        batch_op.drop_column('herramientas')
