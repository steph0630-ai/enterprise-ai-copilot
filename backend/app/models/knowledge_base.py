from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func

from app.database.session import Base


class KnowledgeBase(Base):
    """知识库表：一个用户可建多个知识库（如 HR知识库、产品知识库）"""

    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # 知识库名
    owner_id = Column(Integer, nullable=False)  # 外键 → users.id（谁建的）
    visibility = Column(
        String(20), nullable=False, default="private", server_default="private"
    )
    department = Column(String(50), nullable=True)
    created_time = Column(DateTime(timezone=True), server_default=func.now())


class KnowledgeBaseMember(Base):
    """私有知识库的额外只读成员；仅超级管理员管理。"""

    __tablename__ = "knowledge_base_members"
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "user_id", name="uq_kb_member"),
    )

    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(
        Integer,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
