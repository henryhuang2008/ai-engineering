from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

database_url = get_settings().database_url
engine_options = {"pool_pre_ping": True}
if make_url(database_url).get_backend_name() == "postgresql":
    engine_options["connect_args"] = {"connect_timeout": 5}
engine = create_engine(database_url, **engine_options)
SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)
