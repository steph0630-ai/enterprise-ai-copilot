# 这里 import 所有模型，确保 SQLAlchemy 的 Base.metadata 能"认识"它们
# 否则 create_all 只建被 import 过的表
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.chat_history import ChatHistory
from app.models.order import Order

__all__ = [
    "User",
    "KnowledgeBase",
    "Document",
    "DocumentChunk",
    "ChatHistory",
    "Order",
]
