from pathlib import Path
from alembic.config import Config
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from source.db.db import Base, DATABASE_URL
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
        print("Синхронизация с существующими миграциями...")
        command.upgrade(cfg, "head")
        mc = MigrationContext.configure(connection)
        diff = compare_metadata(mc, Base.metadata)

        if not diff:
            print("Изменений в моделях не найдено. База актуальна.")
            return

        print(f"Обнаружены изменения: {diff}")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")

        try:
            command.revision(
                cfg,
                message=f"auto_migration_{timestamp}",
                autogenerate=True
            )
            print(f"Создан новый файл миграции.")

            command.upgrade(cfg, "head")
            print("База успешно обновлена!")

        except Exception as e:
            print(f"Ошибка при создании миграции: {e}")