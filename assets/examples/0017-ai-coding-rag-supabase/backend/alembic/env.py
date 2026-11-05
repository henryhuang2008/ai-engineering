from logging.config import fileConfig

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

from alembic import context
from app.config import settings
from app.database.models import Base

config = context.config
fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url(*, require_database_url: bool) -> URL:
    database_url = settings.database_url
    if not database_url:
        if require_database_url:
            raise RuntimeError(
                "DATABASE_URL is required for Alembic. Set it in backend/.env "
                "to the Supabase Postgres connection string."
            )
        return URL.create("postgresql+psycopg", host="localhost", database="offline_migration")

    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql", "postgresql+psycopg2"}:
        url = url.set(drivername="postgresql+psycopg")

    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(require_database_url=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    database_url = get_database_url(require_database_url=True)
    connectable = create_engine(database_url, poolclass=NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
