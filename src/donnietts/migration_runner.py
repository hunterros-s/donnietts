from importlib import resources

from alembic import command
from alembic.config import Config

from donnietts.settings import ControllerSettings


def upgrade_database(settings: ControllerSettings) -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)

    config = Config()
    config.set_main_option(
        "script_location",
        str(resources.files("donnietts").joinpath("migrations")),
    )
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")
