"""Agent 的工具：给模型的"说明书"（TOOLS）+ 实际执行函数

关键认知：模型看不见下面的 Python 代码，它只看得见 TOOLS 这份 JSON 说明书。
description 写得好不好，直接决定模型能不能选对工具。
"""

from sqlalchemy.orm import Session

from app.models.order import Order
from app.services.rag_service import rag_service


# ========== 工具说明书（模型只能看到这个） ==========

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "在企业知识库中检索相关文档片段并生成回答，返回答案和来源文件名。"
                "当用户询问公司制度、流程、规定、政策等知识类问题时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "用户的问题或想检索的内容"},
                    "top_k": {"type": "integer", "description": "返回最相关的片段数，默认 3"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_orders",
            "description": (
                "查询订单统计数据。当用户询问订单数量、订单金额等数据类问题时使用。"
                "按部门查询，返回该部门的订单笔数和总金额。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "部门名称，如 销售一部"},
                },
                "required": ["department"],
            },
        },
    },
]


# ========== 实际执行函数（模型看不到这里） ==========

def _search_knowledge(query: str, top_k: int = 3) -> dict:
    """知识类工具：复用 Day 6 的完整 RAG（检索 + 生成 + 出处）"""
    result = rag_service.answer(query, k=top_k)
    return {"answer": result["answer"], "sources": result["sources"]}


def _query_orders(db: Session, department: str) -> dict:
    """数据类工具：查订单表，返回该部门的笔数和总金额"""
    rows = db.query(Order).filter(Order.department == department).all()
    total = round(sum(float(o.amount) for o in rows), 2)
    return {
        "department": department,
        "订单笔数": len(rows),
        "总金额": total,
    }


# ========== 执行器：按名字找到函数并调用 ==========

def run_tool(name: str, arguments: dict, db: Session) -> dict:
    """按工具名分发到具体函数，返回结果（给 Agent 循环用）"""
    if name == "search_knowledge":
        return _search_knowledge(**arguments)
    if name == "query_orders":
        return _query_orders(db=db, **arguments)
    return {"error": f"未知工具：{name}"}
