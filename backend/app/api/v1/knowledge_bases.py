from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user, get_db
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase, KnowledgeBaseMember
from app.models.user import User
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseMemberCreate,
    KnowledgeBaseUpdate,
)
from app.services import knowledge_base_service

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.get("")
def list_knowledge_bases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    knowledge_bases = knowledge_base_service.list_accessible(db, current_user)
    ids = [kb.id for kb in knowledge_bases]
    counts = dict(
        db.query(Document.knowledge_base_id, func.count(Document.id))
        .filter(Document.knowledge_base_id.in_(ids))
        .group_by(Document.knowledge_base_id)
        .all()
    ) if ids else {}
    return [
        {**knowledge_base_service.serialize(kb, current_user), "document_count": counts.get(kb.id, 0)}
        for kb in knowledge_bases
    ]


@router.post("", status_code=201)
def create_knowledge_base(
    data: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    values = data.model_dump()
    if current_user.role == "admin":
        if not current_user.department:
            raise HTTPException(status_code=403, detail="部门管理员尚未分配部门")
        values.update(visibility="department", department=current_user.department)
    kb = KnowledgeBase(owner_id=current_user.id, **values)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return knowledge_base_service.serialize(kb, current_user)


@router.put("/{knowledge_base_id}")
def update_knowledge_base(
    knowledge_base_id: int,
    data: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    kb = knowledge_base_service.get_manageable(db, current_user, knowledge_base_id)
    if current_user.role == "admin":
        kb.name = data.name
    else:
        for key, value in data.model_dump().items():
            setattr(kb, key, value)
        if kb.visibility != "private":
            db.query(KnowledgeBaseMember).filter(
                KnowledgeBaseMember.knowledge_base_id == kb.id
            ).delete()
    db.commit()
    db.refresh(kb)
    return knowledge_base_service.serialize(kb, current_user)


@router.get("/{knowledge_base_id}/members")
def list_members(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    knowledge_base_service.get_manageable(db, current_user, knowledge_base_id)
    rows = (
        db.query(User)
        .join(KnowledgeBaseMember, KnowledgeBaseMember.user_id == User.id)
        .filter(KnowledgeBaseMember.knowledge_base_id == knowledge_base_id)
        .order_by(User.id)
        .all()
    )
    return [
        {"id": u.id, "employee_no": u.employee_no, "name": u.name, "department": u.department}
        for u in rows
    ]


@router.post("/{knowledge_base_id}/members", status_code=201)
def add_member(
    knowledge_base_id: int,
    data: KnowledgeBaseMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    kb = knowledge_base_service.get_manageable(db, current_user, knowledge_base_id)
    if kb.visibility != "private":
        raise HTTPException(status_code=400, detail="只有私有知识库可以添加成员")
    if db.get(User, data.user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if data.user_id == kb.owner_id:
        raise HTTPException(status_code=400, detail="知识库所有者无需重复添加")
    member = (
        db.query(KnowledgeBaseMember)
        .filter(
            KnowledgeBaseMember.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseMember.user_id == data.user_id,
        )
        .first()
    )
    if member is None:
        member = KnowledgeBaseMember(
            knowledge_base_id=knowledge_base_id, user_id=data.user_id
        )
        db.add(member)
        db.commit()
    return {"knowledge_base_id": knowledge_base_id, "user_id": data.user_id}


@router.delete("/{knowledge_base_id}/members/{user_id}")
def remove_member(
    knowledge_base_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    knowledge_base_service.get_manageable(db, current_user, knowledge_base_id)
    deleted = (
        db.query(KnowledgeBaseMember)
        .filter(
            KnowledgeBaseMember.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseMember.user_id == user_id,
        )
        .delete()
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="成员不存在")
    db.commit()
    return {"status": "deleted"}
