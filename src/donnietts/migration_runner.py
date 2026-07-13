from importlib import resources

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from donnietts.settings import ControllerSettings


def migration_config() -> Config:
    config = Config()
    config.set_main_option(
        "script_location",
        str(resources.files("donnietts").joinpath("migrations")),
    )
    return config


def schema_head_revision() -> str:
    revision = ScriptDirectory.from_config(migration_config()).get_current_head()
    if revision is None:
        raise RuntimeError("Database migrations have no head revision")
    return revision


def upgrade_database(settings: ControllerSettings) -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)

    config = migration_config()
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")
