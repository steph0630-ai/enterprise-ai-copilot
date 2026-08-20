"""会话服务：多轮记忆的读写（Day 11，Day 24 加会话列表/完整历史/删除）

职责：
- get_or_create：按 id 找会话，没有就新建一个（写路径）
- get_owned：按 (id AND user_id) 找会话，找不到返回 None（读/删路径）
- list_by_user：某用户的会话列表，按最后活动倒序（Day 24 侧边栏）
- history：取一个会话的消息（默认最近 10 条喂模型；limit=None 取全量给前端）
- append：存一条消息；第一条 user 消息定标题、每次写入刷 updated_at
"""

from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message

# Day 24.5：会话标题 = 第一条 user 消息截前 20 字（DeepSeek 风格，省一次 LLM 调用）。
# 抽成 helper 的原因：append 生成标题、list_by_user 给老会话（title 为 NULL）兜底
# 都要用——截断规则必须一致，否则列表里新老会话的标题长短不一。
_TITLE_MAX = 20


def _make_title(text: str) -> str:
    """把一段话压成会话标题：去换行/多余空白，超 20 字截断加省略号"""
    flat = " ".join(text.strip().split())
    return flat[:_TITLE_MAX] + ("…" if len(flat) > _TITLE_MAX else "")


class ConversationService:
    def get_or_create(
        self, conversation_id: str, user_id: int | None, db: Session
    ) -> Conversation:
        """找到自己的会话；前端没给 id / 给了不存在的 id / 是别人的 → 新建（Day 12）

        隔离要点：按 (id AND user_id) 查——拿别人的会话 id 来问，也只会开新会话，
        绝不会读到别人的对话历史。
        """
        if conversation_id and user_id:
            conv = self.get_owned(conversation_id, user_id, db)
            if conv:
                return conv
        conv = Conversation(id=conversation_id or str(uuid4()), user_id=user_id)
        db.add(conv)
        db.commit()
        return conv

    def get_owned(
        self, conversation_id: str, user_id: int, db: Session
    ) -> Conversation | None:
        """按 (id AND user_id) 找会话，不是自己的返回 None（Day 24）

        详情/删除的权限校验都用它：别人的会话 id 在这里查不到 → 接口层 404，
        不泄露"这个会话存不存在"。
        """
        return (
            db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .first()
        )

    def list_by_user(
        self, user_id: int, db: Session, limit: int = 50
    ) -> list[dict]:
        """该用户的会话列表，按"最后活动"倒序（刚聊完的排最前）——Day 24 侧边栏

        order_by 用 COALESCE(updated_at, created_at)：Day 24 之前的老会话
        updated_at 是 NULL，兜底到创建时间排序（老会话自然沉底）。
        不能裸 ORDER BY updated_at DESC——SQLite 把 NULL 排最前、MySQL 排最后，
        跨库行为不一致，测试/生产结果会对不上。

        Day 24.5：title 用 COALESCE(title, 第一条 user 消息) 兜底——老会话
        title 是 NULL（Day 24 之前没有标题逻辑），但用户希望侧边栏看到的是
        "第一个问题"而不是"未命名对话"（DeepSeek 风格）。读时计算，不用跑脚本
        补数据，新老会话统一走同一个截断规则（_make_title）。空会话没有消息，
        兜底仍为 NULL → 前端显示"未命名对话"（无内容可当标题，合理）。
        """
        # 相关子查询：每个会话的第一条 user 消息（最老的那条），给 title 兜底用
        first_user_msg = (
            db.query(Message.content)
            .filter(
                Message.conversation_id == Conversation.id,
                Message.role == "user",
            )
            .order_by(Message.id)
            .limit(1)
            .scalar_subquery()
        )
        rows = (
            db.query(
                Conversation.id,
                Conversation.created_at,
                Conversation.updated_at,
                func.coalesce(Conversation.title, first_user_msg).label("title"),
            )
            .filter(Conversation.user_id == user_id)
            .order_by(func.coalesce(Conversation.updated_at, Conversation.created_at).desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "title": _make_title(r.title) if r.title else None,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ]

    def history(
        self, conv: Conversation, db: Session, limit: int | None = 10
    ) -> list[dict]:
        """取会话消息，按旧→新排好

        limit=10（默认）：最近 10 条 = 5 轮问答，喂模型当上下文；
        limit=None：全量，前端"打开历史会话"要展示完整对话。
        坑点：直接 order_by(id.desc()).limit(limit) 拿到的是"最新在前"，
        必须再 reverse() 一次才是"旧在前"，模型读起来才顺。
        """
        q = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.id.desc())
        )
        if limit is not None:
            q = q.limit(limit)
        msgs = q.all()
        msgs.reverse()
        return [{"role": m.role, "content": m.content} for m in msgs]

    def append(self, conv: Conversation, role: str, content: str, db: Session) -> None:
        """往会话里存一条消息，立即提交（不然 get_db 关闭时没保存）

        Day 24 两件附加事：
        - 第一条 user 消息 → 定会话标题（截前 20 字，省一次 LLM 调用的取舍；
          规则和 list_by_user 兜底共用 _make_title，保证新老一致）
        - 每次写入都显式刷 updated_at。坑：模型的 onupdate=func.now() 只在
          conv 字段实际变更时触发，title 定完后的 append 没字段变更就不会发
          UPDATE，会话排序不动——所以这里显式赋值，强制 conv 进 UPDATE。
        """
        if role == "user" and not conv.title:
            conv.title = _make_title(content)
        conv.updated_at = func.now()
        db.add(Message(conversation_id=conv.id, role=role, content=content))
        db.commit()


# 模块级单例
conversation_service = ConversationService()
