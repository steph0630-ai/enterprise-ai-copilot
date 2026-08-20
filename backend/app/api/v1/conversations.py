"""会话管理接口：列表 / 详情 / 删除（Day 24 前端刷新不丢历史）

三个接口都在 /api/v1/agent/conversations 下，全要登录（get_current_user）。
权限模型：只能看/删自己的会话——get_owned 按 (id AND user_id) 查，
拿别人的会话 id 来访问 → 404（不泄露存在性，和 Day 12 写路径的隔离思想一致）。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.conversation_service import conversation_service

router = APIRouter(prefix="/agent/conversations", tags=["conversations"])


def _get_owned_or_404(conversation_id: str, user: User, db: Session):
    """取"自己的会话"，不是自己的/不存在的 → 404（详情和删除共用）"""
    conv = conversation_service.get_owned(conversation_id, user.id, db)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


@router.get("")
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当前用户的会话列表（最近 50 个，按最后活动倒序）——侧边栏数据源"""
    return conversation_service.list_by_user(current_user.id, db)


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取某会话的完整消息历史（前端打开历史会话用）

    limit=None → 全量；不是自己的会话 → 404。
    """
    conv = _get_owned_or_404(conversation_id, current_user, db)
    return {
        "id": conv.id,
        "title": conv.title,
        "messages": conversation_service.history(conv, db, limit=None),
    }


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除会话（消息级联一起删，模型 cascade="all, delete-orphan"）"""
    conv = _get_owned_or_404(conversation_id, current_user, db)
    db.delete(conv)
    db.commit()
    return {"ok": True}
