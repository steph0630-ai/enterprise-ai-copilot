from sqlalchemy import Column, Integer, String, DateTime, func

from app.database.session import Base


class Document(Base):
    """文档表：一个知识库里有多个文档（上传的 PDF/文档）"""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, nullable=False)  # 外键 → knowledge_bases.id（属于哪个知识库）
    filename = Column(String(255), nullable=False)  # 文件名
    status = Column(String(20), default="pending")  # pending处理中 / done已完成
    created_time = Column(DateTime(timezone=True), server_default=func.now())
