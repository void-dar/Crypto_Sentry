import asyncio
from logging.config import fileConfig
import os
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from dotenv import load_dotenv
from alembic import context
import alembic_postgresql_enum

load_dotenv()
# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import your models' metadata
from src.a_c_d_backend.db.models import SQLModel
target_metadata = SQLModel.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and without an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    load_dotenv()
    # Build DB URL from env vars
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_NAME")
    db_driver = "asyncpg"

    connect_url = f"postgresql+{db_driver}://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    # Override/ensure URL in config
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = connect_url

    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    def run_migrations_connection(connection):
        # All Alembic ops happen synchronously on this connection via run_sync
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Important for PostgreSQL schema changes (enums, etc.)
        )

        with context.begin_transaction():
            context.run_migrations()

    async def run_async_migrations():
        async with connectable.connect() as connection:
            # Run the sync-style migration logic inside run_sync
            await connection.run_sync(run_migrations_connection)

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    do_run_migrations_online()