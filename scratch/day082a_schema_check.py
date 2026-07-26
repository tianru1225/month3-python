import sqlite3

from sqlalchemy import create_engine

from app.db.base import Base

engine = create_engine("sqlite:///scratch/day082a_check.db")
Base.metadata.drop_all(bind = engine)
Base.metadata.create_all(bind=engine)

conn = sqlite3.connect("scratch/day082a_check.db")
try:
    tables = conn.execute(
        "select name from sqlite_master where type = 'table' order by name"
    ).fetchall()
    print("tables:",tables)
    indexes = conn.execute(
        "select name from sqlite_master where type = 'index' order by name"
    ).fetchall()
    print("indexes:",indexes)
finally:
    conn.close()