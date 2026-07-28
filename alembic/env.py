import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from chalk.db.models import Base
import chalk.mlb.models  # noqa: F401  — registers MLB tables on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Prefer DATABASE_URL from environment, then chalk settings (which reads .env),
# then fall back to alembic.ini — so migrations work against any target DB.
_db_url = os.environ.get("DATABASE_URL")
if not _db_url:
    try:
        from chalk.config import settings
        _db_url = settings.DATABASE_URL
    except Exception as exc:
        # Falling back to alembic.ini is intentional, but say so. Swallowing
        # this silently meant a broken chalk.config import looked identical to
        # "DATABASE_URL simply wasn't set", and migrations would then run
        # against whatever alembic.ini points at - which is localhost.
        print(f"alembic: could not read DATABASE_URL from chalk.config ({exc}); falling back to alembic.ini")
if _db_url:
    config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
