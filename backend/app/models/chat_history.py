from sqlalchemy import Column, Integer, Text, DateTime, func

from app.database.session import Base


class ChatHistory(Base):
    """聊天记录表：记录用户每次问答，用于查看历史对话"""

    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)  # 外键 → users.id（谁问的）
    question = Column(Text, nullable=False)  # 用户问题
    answer = Column(Text, nullable=False)  # 系统回答
    created_time = Column(DateTime(timezone=True), server_default=func.now())
