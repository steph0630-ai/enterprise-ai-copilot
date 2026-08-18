"""Agent 接口：POST /api/v1/agent/chat —— 会判断 + 会调工具的回答（Day 7）

Day 10 新增：POST /api/v1/agent/chat/stream —— 流式版（SSE 打字机）
Day 11 新增：conversation_id 多轮记忆 —— 问前读历史、答后存库
"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.agent import agent_service
from app.api.deps import get_db
from app.models.conversation import Conversation
from app.services.conversation_service import conversation_service

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    """请求体：用户问题 + 会话 id（空 = 新建会话）"""

    query: str
    conversation_id: str = ""


def _build_messages(req: AgentRequest, db: Session) -> tuple[list[dict], Conversation]:
    """多轮记忆的核心：找到会话 → 读历史 → 拼出"历史 + 当前问题"

    返回 (messages, conv)：messages 喂给 Agent，conv 用来存这一轮的新问答。
    """
    conv = conversation_service.get_or_create(req.conversation_id, db)
    history = conversation_service.history(conv, db)
    messages = history + [{"role": "user", "content": req.query}]
    return messages, conv


@router.post("/chat")
def agent_chat(req: AgentRequest, db: Session = Depends(get_db)):
    """Agent 问答：问题 → 判断任务 → 调工具（知识/RAG 或 数据/SQL）→ 回答"""
    messages, conv = _build_messages(req, db)
    result = agent_service.answer(messages, db=db)
    # 问完了，把这一轮存进会话（下次提问它就是"历史"）
    conversation_service.append(conv, "user", req.query, db)
    conversation_service.append(conv, "assistant", result["answer"], db)
    return {"query": req.query, "conversation_id": conv.id, **result}


@router.post("/chat/stream")
def agent_chat_stream(req: AgentRequest, db: Session = Depends(get_db)):
    """流式版：答案逐字返回（SSE 打字机效果），前端用 fetch 流式读取

    协议：text/event-stream，一帧一条 `data: {JSON}\n\n`：
        {"type": "conv",  "conversation_id": "..."}  会话 id（第一帧，前端记下来）
        {"type": "token", "content": "..."}   模型吐的一段文字
        {"type": "tool",  "name": "..."}      调用了工具
        {"type": "done",  "tools_used": [...]} 结束
        {"type": "error", "message": "..."}   出错
    """
    def generate():
        try:
            messages, conv = _build_messages(req, db)
            # 第一帧先把会话 id 推给前端，它要拿这个号发后面的问题
            yield (
                f"data: {json.dumps({'type': 'conv', 'conversation_id': conv.id}, ensure_ascii=False)}\n\n"
            )

            answer_parts: list[str] = []
            for event in agent_service.answer_stream(messages, db=db):
                if event["type"] == "token":
                    answer_parts.append(event["content"])  # 先攒着，流完才能整段存库
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # 流完了，把这一轮存进会话（下次提问它就是"历史"）
            conversation_service.append(conv, "user", req.query, db)
            conversation_service.append(conv, "assistant", "".join(answer_parts), db)
        except Exception as e:
            # 整个流崩了也要给前端一个交代，不能断在中间
            yield (
                f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(generate(), media_type="text/event-stream")
