from source.db.db import engine
from source.migrations.models import Base

def init_db():
    Base.metadata.create_all(bind=engine)