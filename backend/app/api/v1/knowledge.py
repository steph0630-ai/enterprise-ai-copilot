"""知识检索接口：POST /api/v1/knowledge/search"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.retrieval_service import retrieval_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class SearchRequest(BaseModel):
    """请求体：用户的问题 + 返回条数"""

    query: str
    top_k: int = Field(default=3, ge=1, le=10)  # 限制 1~10，防止有人要 100000 条


@router.post("/search")
def search(req: SearchRequest):
    """检索：输入问题，返回最相关的文档片段（RAG 第一阶段）"""
    results = retrieval_service.search(req.query, k=req.top_k)
    return {"query": req.query, "results": results}
