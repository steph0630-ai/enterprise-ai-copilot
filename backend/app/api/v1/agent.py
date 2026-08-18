"""Agent 接口：POST /api/v1/agent/chat —— 会判断 + 会调工具的回答（Day 7）"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.agent import agent_service
from app.api.deps import get_db

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    """请求体：用户问题"""

    query: str


@router.post("/chat")
def agent_chat(req: AgentRequest, db: Session = Depends(get_db)):
    """Agent 问答：问题 → 判断任务 → 调工具（知识/RAG 或 数据/SQL）→ 回答"""
    result = agent_service.answer(req.query, db=db)
    return {"query": req.query, **result}
