from sqlalchemy import Column, Integer, String, DateTime, func

from app.database.session import Base


class Document(Base):
    """文档表：一个知识库里有多个文档（上传的 PDF/文档）"""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, nullable=False)  # 外键 → knowledge_bases.id
    filename = Column(String(255), nullable=False)  # 文件名
    file_path = Column(String(500), nullable=False)  # 文件磁盘路径（storage/files/xxx.pdf）
    status = Column(String(20), default="uploaded")  # uploaded/uploading/processing/processed/failed（Day 18 引入异步状态机）
    error_message = Column(String(500), nullable=True)  # Day 18：入库失败的原因，成功为 None
    created_time = Column(DateTime(timezone=True), server_default=func.now())
