import sqlite3
conn = sqlite3.connect("dev.db")
try:
    print(conn.execute("select name from sqlite_master where type='table' order by name").fetchall())
finally:
    conn.close()