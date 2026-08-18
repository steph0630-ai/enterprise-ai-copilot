"""会话服务：多轮记忆的读写（Day 11）

三个职责：
- get_or_create：按 id 找会话，没有就新建一个
- history：取一个会话里最近 N 条消息（旧→新排好）
- append：往会话里存一条消息（user 的问题 / assistant 的回答）
"""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message


class ConversationService:
    def get_or_create(self, conversation_id: str, db: Session) -> Conversation:
        """找到会话；前端没给 id / 给了不存在的 id → 新建，返回它"""
        if conversation_id:
            conv = db.get(Conversation, conversation_id)
            if conv:
                return conv
        conv = Conversation(id=conversation_id or str(uuid4()))
        db.add(conv)
        db.commit()
        return conv

    def history(self, conv: Conversation, db: Session, limit: int = 10) -> list[dict]:
        """取最近 limit 条消息（默认 10 条 = 5 轮问答），按旧→新排好

        坑点：直接 order_by(id.desc()).limit(limit) 拿到的是"最新在前"，
        必须再 reverse() 一次才是"旧在前"，模型读起来才顺。
        """
        msgs = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.id.desc())
            .limit(limit)
            .all()
        )
        msgs.reverse()
        return [{"role": m.role, "content": m.content} for m in msgs]

    def append(self, conv: Conversation, role: str, content: str, db: Session) -> None:
        """往会话里存一条消息，立即提交（不然 get_db 关闭时没保存）"""
        db.add(Message(conversation_id=conv.id, role=role, content=content))
        db.commit()


# 模块级单例
conversation_service = ConversationService()
