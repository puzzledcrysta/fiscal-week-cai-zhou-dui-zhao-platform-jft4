import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, source BLOB NOT NULL, book BLOB NOT NULL,
  result TEXT NOT NULL, created TEXT NOT NULL, promotion BLOB
);
CREATE TABLE IF NOT EXISTS reviews (
  run_id TEXT NOT NULL REFERENCES runs(id), version INTEGER NOT NULL,
  decision TEXT NOT NULL, note TEXT NOT NULL, changed TEXT NOT NULL,
  PRIMARY KEY(run_id,version)
);
"""


def upgrade(db):
    """旧批次库补上促销日期列；已有记录保持不变，重跑仍按原指纹复用。"""
    columns = {row['name'] for row in db.execute('PRAGMA table_info(runs)')}
    if 'promotion' not in columns:
        db.execute('ALTER TABLE runs ADD COLUMN promotion BLOB')


@contextmanager
def connection():
    path = Path(settings.DB)
    path.parent.mkdir(parents=True,exist_ok=True)
    db = sqlite3.connect(path,timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys = ON')
        db.executescript(SCHEMA)
        upgrade(db)
        with db:
            yield db
    finally:
        db.close()
