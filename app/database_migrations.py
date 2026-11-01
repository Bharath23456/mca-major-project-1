from pathlib import Path

from alembic import command
from alembic.config import Config

from app.settings import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def migrate_database(database_url: str | None = None, revision: str = "head") -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location", str(PROJECT_ROOT / "app" / "migrations").replace("\\", "/")
    )
    config.set_main_option(
        "sqlalchemy.url", (database_url or settings.database_url).replace("%", "%%")
    )
    if revision == "base":
        command.downgrade(config, revision)
    else:
        command.upgrade(config, revision)
