import sqlite3
conn = sqlite3.connect("dev.db")
try:
    tables = conn.execute("select name from sqlite_master where type = 'table' order by name").fetchall()
    print(tables)
    schema = conn.execute("select sql from sqlite_master where type = 'table' and name = 'users'").fetchone()
    print(schema[0])
finally:
    conn.close()