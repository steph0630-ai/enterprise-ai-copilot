"""对话接口：POST /api/v1/chat —— 问知识，返回「答案 + 出处」（Day 6）"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.rag_service import rag_service

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """请求体：用户问题 + 检索条数"""

    query: str
    top_k: int = Field(default=3, ge=1, le=5)  # 对话场景片段别给太多，省 token


@router.post("")
def chat(req: ChatRequest):
    """RAG 问答：问题 → 检索 → 拼 Prompt → LLM 生成 → 答案 + 出处"""
    result = rag_service.answer(req.query, k=req.top_k)
    return {"query": req.query, **result}
