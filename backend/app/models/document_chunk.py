from sqlalchemy import Column, Integer, String, Text, DateTime, func

from app.database.session import Base


class DocumentChunk(Base):
    """片段表：一个文档切成多个 chunk（RAG 检索的最小单位）"""

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False)  # 外键 → documents.id（属于哪个文档）
    content = Column(Text, nullable=False)  # 片段文本内容（用 Text，可能很长）
    chunk_index = Column(Integer, nullable=False)  # 第几个片段（保持顺序）
    vector_id = Column(String(255), nullable=True)  # 指向向量库里对应的向量
    created_time = Column(DateTime(timezone=True), server_default=func.now())
