from datetime import datetime,timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime,ForeignKey,Index,String
from sqlalchemy.orm import Mapped,mapped_column,relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.message import Message
    
def utc_now() ->datetime:
    return datetime.now(timezone.utc)
    
class Conversation(Base):
    __tablename__="conversations"
    __table_args__=(
        Index("ix_conversations_user_id","user_id"),
        Index("ix_conversations_user_id_created_at","user_id","created_at"),
    )
    
    id: Mapped[int]=mapped_column(primary_key=True,index = True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"),nullable=False)
    title: Mapped[str] = mapped_column(String(200),nullable = False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade = "all,delete-orphan",
    )