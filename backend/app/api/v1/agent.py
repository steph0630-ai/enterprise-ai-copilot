"""Agent 接口：POST /api/v1/agent/chat —— 会判断 + 会调工具的回答（Day 7）

Day 10 新增：POST /api/v1/agent/chat/stream —— 流式版（SSE 打字机）
Day 11 新增：conversation_id 多轮记忆 —— 问前读历史、答后存库
Day 12 新增：登录才能用（get_current_user）+ 会话绑用户 + system 消息带用户身份
"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.agent import agent_service
from app.api.deps import ADMIN_ROLES, get_current_user, get_db
from app.models.conversation import Conversation
from app.models.user import User
from app.services.conversation_service import conversation_service
from app.services import knowledge_base_service

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    """请求体：用户问题 + 会话 id（空 = 新建会话）"""

    query: str
    conversation_id: str = ""
    knowledge_base_id: int | None = None


def _build_messages(
    req: AgentRequest, user: User, db: Session
) -> tuple[list[dict], Conversation]:
    """拼出给 Agent 的完整消息列表（Day 11 多轮 + Day 12 用户身份 + Day 19 防幻觉规则）

    结构：system（你是谁/什么权限/怎么干活） + 历史（自己的会话） + 当前问题
    返回 (messages, conv)：messages 喂给 Agent，conv 用来存这一轮的新问答。
    """
    # 会话按 user_id 隔离：拿别人的会话 id 来问只会开新会话
    conv = conversation_service.get_or_create(req.conversation_id, user.id, db)
    history = conversation_service.history(conv, db)
    # 管理端显示"全部部门"，普通用户没分部门才显示"未分配"（Day 17 顺手修）
    dept_desc = user.department or ("全部部门" if user.role in ADMIN_ROLES else "未分配")
    system = {
        "role": "system",
        "content": (
            f"你是企业智能助手。当前用户：{user.name}（工号 {user.employee_no}），"
            f"角色：{user.role}，部门：{dept_desc}。\n"
            # Day 19 修：原来 system 只有身份没有行为规则，模型会把"工具调用方式"
            # 这类问题当成"关于系统自身的元问题"，凭自己的认知直接答、不查知识库。
            # 教训：抽象规则（"知识类问题要查库"）压不过模型的强先验，必须配一个
            # 具体示例（few-shot）才能真正掰过来——光讲道理不如举一个例子。
            "工作规则：\n"
            "1. 内容性问题（概念、原理、方法、教程、课程、制度、流程等）"
            "一律先调用 search_knowledge 从企业知识库检索，再依据检索结果作答，"
            "不得凭自己的知识或对工具的了解直接回答。\n"
            "特别地：凡是涉及公司具体数字/金额/余额/报表数据的问题"
            "（如\"XX科目期末余额是多少\"），都是内容性问题，必须先检索后回答；"
            "检索结果里没有就明确说\"知识库中没有相关内容\"，禁止编造数字。\n"
            "2. 只有用户明确询问\"你这个系统/你的工具/平台架构\"（如\"你们用什么技术栈\"）时，"
            "才可以不检索、直接回答。\n"
            "3. 调用工具后，严格依据工具返回的内容作答；结果里没有的信息，"
            "明确说\"知识库中没有相关内容\"，不要编造、不要补充。\n"
            "4. 数据类问题调用 query_data 查询数据库，同样以查询结果为准。\n"
            "5. 调用 search_knowledge 时按问题类型选 top_k：列举/概括类问题"
            "（\"有哪些\"\"列出\"\"总结\"）设 8~10 召回更全，具体事实类用 3。\n"
            "6. 回答中列出来源文件时，只列出你实际引用的来源，不要罗列工具返回的所有来源。\n"
            # Day 24.6：冲突文档处理——防止模型悄悄二选一或糅合（幻觉的一种）
            "7. 不同来源的资料说法不一致时，不要自行选择其中一个或糅合，明确告诉用户"
            "\"不同资料说法不一致\"，分别列出各来源的说法并注明出处，让用户自己核对判断。\n"
            "8. 财务金额必须保留原文单位；原文是万元就写万元，不要自行改写成元，"
            "除非用户明确要求换算。\n"
            "9. 同一科目若在概览表和附注明细表里都出现，优先按附注/明细表的原始金额回答，"
            "并说明概览表可能是万元口径或四舍五入后的摘要。\n"
            "示例：用户问\"工具调用方式\"\"函数调用是什么\"\"Agent 怎么用工具\"，"
            "指的是知识库文档里的内容，必须先调用 search_knowledge，"
            "不能讲我们自己的 search_knowledge/query_data 工具本身。"
        ),
    }
    messages = [system] + history + [{"role": "user", "content": req.query}]
    return messages, conv


@router.post("/chat")
def agent_chat(
    req: AgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # Day 12：没登录就 401
):
    """Agent 问答：问题 → 判断任务 → 调工具（知识/RAG 或 数据/SQL）→ 回答"""
    messages, conv = _build_messages(req, current_user, db)
    document_ids = knowledge_base_service.accessible_document_ids(
        db, current_user, req.knowledge_base_id
    )
    result = agent_service.answer(
        messages, db=db, user=current_user, document_ids=document_ids
    )
    # 问完了，把这一轮存进会话（下次提问它就是"历史"）
    conversation_service.append(conv, "user", req.query, db)
    conversation_service.append(conv, "assistant", result["answer"], db)
    return {"query": req.query, "conversation_id": conv.id, **result}


@router.post("/chat/stream")
def agent_chat_stream(
    req: AgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # Day 12：没登录就 401
):
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
            messages, conv = _build_messages(req, current_user, db)
            document_ids = knowledge_base_service.accessible_document_ids(
                db, current_user, req.knowledge_base_id
            )
            # 第一帧先把会话 id 推给前端，它要拿这个号发后面的问题
            yield (
                f"data: {json.dumps({'type': 'conv', 'conversation_id': conv.id}, ensure_ascii=False)}\n\n"
            )

            answer_parts: list[str] = []
            for event in agent_service.answer_stream(
                messages, db=db, user=current_user, document_ids=document_ids
            ):
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
