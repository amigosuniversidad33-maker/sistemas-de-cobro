"""Entorno de migraciones Alembic. Usa DATABASE_URL de la configuración (.env)."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401  (registra las tablas)
from app.config import get_settings
from app.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
_url = get_settings().database_url_migraciones or get_settings().database_url
config.set_main_option("sqlalchemy.url", _url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True,
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.",
                                    poolclass=pool.NullPool)
    with conectable.connect() as conexion:
        context.configure(connection=conexion, target_metadata=target_metadata, compare_type=True,
                          render_as_batch=conexion.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
