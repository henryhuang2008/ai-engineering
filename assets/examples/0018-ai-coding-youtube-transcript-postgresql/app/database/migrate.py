from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import get_settings

ALEMBIC_CONFIG_PATH = Path(__file__).resolve().parent / "alembic.ini"


def upgrade_to_head() -> None:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.set_main_option(
        "sqlalchemy.url",
        get_settings().database_url.replace("%", "%%"),
    )
    command.upgrade(config, "head")


def main() -> None:
    upgrade_to_head()
    print("Database migrations are up to date.")


if __name__ == "__main__":
    main()
