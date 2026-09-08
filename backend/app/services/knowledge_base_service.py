from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase, KnowledgeBaseMember
from app.models.user import User


def accessible_query(db: Session, user: User) -> Query:
    """服务端权限单一入口：所有知识检索都必须从这里得到可访问范围。"""
    if user.role == "super_admin":
        return db.query(KnowledgeBase)
    member_ids = db.query(KnowledgeBaseMember.knowledge_base_id).filter(
        KnowledgeBaseMember.user_id == user.id
    )
    rules = [
        KnowledgeBase.visibility == "public",
    ]
    if user.department:
        rules.append(
            (KnowledgeBase.visibility == "department")
            & (KnowledgeBase.department == user.department)
        )
    if user.role != "admin":
        rules.extend(
            [
                KnowledgeBase.owner_id == user.id,
                (KnowledgeBase.visibility == "private")
                & KnowledgeBase.id.in_(member_ids),
            ]
        )
    return db.query(KnowledgeBase).filter(or_(*rules))


def list_accessible(db: Session, user: User) -> list[KnowledgeBase]:
    return accessible_query(db, user).order_by(KnowledgeBase.id).all()


def get_accessible(db: Session, user: User, knowledge_base_id: int) -> KnowledgeBase:
    kb = accessible_query(db, user).filter(KnowledgeBase.id == knowledge_base_id).first()
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在或无权访问")
    return kb


def get_manageable(db: Session, user: User, knowledge_base_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, knowledge_base_id)
    if kb is None or not can_manage(user, kb):
        raise HTTPException(status_code=404, detail="知识库不存在或无权管理")
    return kb


def manageable_ids(db: Session, user: User) -> list[int]:
    q = db.query(KnowledgeBase.id)
    if user.role == "admin":
        q = q.filter(
            KnowledgeBase.visibility == "department",
            KnowledgeBase.department == user.department,
        )
    elif user.role != "super_admin":
        return []
    return [row[0] for row in q.all()]


def can_manage(user: User, kb: KnowledgeBase) -> bool:
    return user.role == "super_admin" or (
        user.role == "admin"
        and bool(user.department)
        and kb.visibility == "department"
        and kb.department == user.department
    )


def accessible_document_ids(
    db: Session, user: User, knowledge_base_id: int | None = None
) -> list[int]:
    # ponytail: ID 过滤保持单机实现简单；文档到万级后改成向量库 ACL metadata/分区。
    if knowledge_base_id is not None:
        get_accessible(db, user, knowledge_base_id)
        knowledge_base_ids = [knowledge_base_id]
    else:
        knowledge_base_ids = [kb.id for kb in list_accessible(db, user)]
    if not knowledge_base_ids:
        return []
    q = db.query(Document.id).filter(
        Document.knowledge_base_id.in_(knowledge_base_ids),
        Document.status == "processed",
    )
    return [row[0] for row in q.all()]


def serialize(kb: KnowledgeBase, user: User) -> dict:
    return {
        "id": kb.id,
        "name": kb.name,
        "owner_id": kb.owner_id,
        "visibility": kb.visibility,
        "department": kb.department,
        "can_manage": can_manage(user, kb),
        "created_time": kb.created_time,
    }
