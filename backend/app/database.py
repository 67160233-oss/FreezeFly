import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LEGACY_DB = BASE_DIR / "sql_app.db"


def _default_database_url() -> str:
    """ฐานข้อมูลใหม่อยู่ที่ backend/data/sql_app.db
    ถ้ายังไม่ได้ย้าย แต่มีไฟล์เดิม backend/sql_app.db อยู่ จะใช้ไฟล์เดิมต่อไปก่อน"""
    new_db = DATA_DIR / "sql_app.db"
    if not new_db.exists() and LEGACY_DB.exists():
        return f"sqlite:///{LEGACY_DB.as_posix()}"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{new_db.as_posix()}"


SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL") or _default_database_url()

_connect_args = (
    {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}
)
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()