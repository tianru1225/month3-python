from app.db.base import Base
from app.db.session import SessionLocal,engine
from app.models.user import User
Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    user = User(username = "alice",email = "aiice@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    found = db.query(User).filter(User.username == "alice").first()
    print(found.id,found.username,found.email)
finally:
    db.close()