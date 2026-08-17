from sqlalchemy import Column, Integer, String, DateTime, func

from app.database.session import Base


class KnowledgeBase(Base):
    """知识库表：一个用户可建多个知识库（如 HR知识库、产品知识库）"""

    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # 知识库名
    owner_id = Column(Integer, nullable=False)  # 外键 → users.id（谁建的）
    created_time = Column(DateTime(timezone=True), server_default=func.now())
