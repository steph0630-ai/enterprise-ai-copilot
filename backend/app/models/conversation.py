"""对话记忆模型：conversations（会话）+ messages（消息）两张表（Day 11）

为什么新建而不是复用 chat_history：
- chat_history 是"审计日志"（谁·何时·问了什么，平铺一条条），给管理员看历史用；
- conversations + messages 是"对话结构"（一个会话多轮、带 role），喂给模型当上下文用。
职责不同，表就按职责分开——这是数据库设计的基本功。
"""

from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database.session import Base


class Conversation(Base):
    """一个会话 = 一段连续的对话。id 由前端生成（uuid），后端只认这个号。"""

    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",  # 删会话时连消息一起删
    )


class Message(Base):
    """会话里的一条消息：user 的问题 / assistant 的回答"""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36), ForeignKey("conversations.id"), nullable=False, index=True
    )
    role = Column(String(20), nullable=False)  # "user" / "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")
