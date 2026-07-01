from sqlalchemy import inspect
from app.db.base import Base
from app.db.session import engine
from app.models.user import User
Base.metadata.create_all(bind=engine)
print(User.__tablename__)
print(Base.metadata.tables.keys())
print(inspect(engine).get_table_names())
print("tables created")