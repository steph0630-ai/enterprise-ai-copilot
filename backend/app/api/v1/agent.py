"""Agent 接口：POST /api/v1/agent/chat —— 会判断 + 会调工具的回答（Day 7）

Day 10 新增：POST /api/v1/agent/chat/stream —— 流式版（SSE 打字机）
"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
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


@router.post("/chat/stream")
def agent_chat_stream(req: AgentRequest, db: Session = Depends(get_db)):
    """流式版：答案逐字返回（SSE 打字机效果），前端用 fetch 流式读取

    协议：text/event-stream，一帧一条 `data: {JSON}\n\n`：
        {"type": "token", "content": "..."}   模型吐的一段文字
        {"type": "tool",  "name": "..."}      调用了工具
        {"type": "done",  "tools_used": [...]} 结束
        {"type": "error", "message": "..."}   出错
    """
    def generate():
        try:
            for event in agent_service.answer_stream(req.query, db=db):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            # 整个流崩了也要给前端一个交代，不能断在中间
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
