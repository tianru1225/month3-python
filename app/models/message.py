from datetime import datetime,timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime,ForeignKey,Index,String,Text
from sqlalchemy.orm import Mapped,mapped_column,relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    
def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Message(Base):
    __tablename__="messages"
    __table_args__=(
        Index("ix_messages_conversation_id","conversation_id"),
        Index("ix_messages_conversation_created_at","conversation_id","created_at") 
    )

    id: Mapped[int] = mapped_column(primary_key = True,index = True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"),nullable=False)
    role: Mapped[str] = mapped_column(String(20),nullable=False)
    content: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utc_now)

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages"
    )