"""知识检索接口：POST /api/v1/knowledge/search"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services import knowledge_base_service
from app.services.retrieval_service import retrieval_service

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(get_current_user)],
)


class SearchRequest(BaseModel):
    """请求体：用户的问题 + 返回条数"""

    query: str
    top_k: int = Field(default=3, ge=1, le=10)  # 限制 1~10，防止有人要 100000 条
    knowledge_base_id: int | None = None


@router.post("/search")
def search(
    req: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检索：输入问题，返回最相关的文档片段（RAG 第一阶段）"""
    document_ids = knowledge_base_service.accessible_document_ids(
        db, current_user, req.knowledge_base_id
    )
    results = retrieval_service.search(req.query, k=req.top_k, document_ids=document_ids)
    return {"query": req.query, "results": results}
