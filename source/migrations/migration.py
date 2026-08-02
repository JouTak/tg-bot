from pathlib import Path
from alembic.config import Config
from alembic import command
from alembic.util.exc import CommandError
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from source.db.db import Base, DATABASE_URL
from source.app_logging import logger
import datetime

def get_alembic_config():
    base_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = base_dir / "alembic.ini"

    cfg = Config(str(ini_path))

    cfg.attributes['configure_logger'] = False
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    cfg.set_main_option("script_location", str(base_dir / "alembic"))
    return cfg


def auto_migrate():
    cfg = get_alembic_config()
    db_url = cfg.get_main_option("sqlalchemy.url")
    engine = create_engine(db_url)

    with engine.connect() as connection:
        logger.info("Синхронизация с существующими миграциями...")
        try:
            command.upgrade(cfg, "head")
        except CommandError as e:
            if "Can't locate revision identified by" not in str(e):
                raise

            logger.info(
                "Обнаружена неизвестная ревизия Alembic в базе. "
                "Очищаем alembic_version и пересинхронизируемся с текущим head."
            )
            with engine.connect() as conn:
                if inspect(conn).has_table("alembic_version"):
                    conn.execute(text("DELETE FROM alembic_version"))
                    conn.commit()

            command.stamp(cfg, "head")

        mc = MigrationContext.configure(connection)
        diff = compare_metadata(mc, Base.metadata)

        if not diff:
            logger.info("Изменений в моделях не найдено. База актуальна.")
            return

        logger.info(f"Обнаружены изменения: {diff}")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")

        try:
            command.revision(
                cfg,
                message=f"auto_migration_{timestamp}",
                autogenerate=True
            )
            logger.info(f"Создан новый файл миграции.")

            command.upgrade(cfg, "head")
            logger.info("База успешно обновлена!")

        except Exception as e:
            logger.error(f"Ошибка при создании миграции: {e}")