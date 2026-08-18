"""Agent 的工具：给模型的"说明书"（TOOLS）+ 实际执行函数

关键认知：模型看不见下面的 Python 代码，它只看得见 TOOLS 这份 JSON 说明书。
description 写得好不好，直接决定模型能不能选对工具。
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

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
            "name": "query_data",
            "description": (
                "根据用户的问题，针对 orders 表生成一条 SELECT 语句并执行，返回查询结果。"
                "当用户询问订单数量、金额等数据类问题时使用。\n"
                "orders 表结构：\n"
                "- id: INTEGER，主键\n"
                "- department: VARCHAR(50)，部门名称，如 销售一部、销售二部、市场部\n"
                "- amount: DECIMAL(10,2)，订单金额\n"
                "- created_at: DATETIME，下单时间（示例数据都是 2026 年 8 月）\n"
                "规则：只允许生成 SELECT 语句，禁止 DELETE/UPDATE/INSERT/DROP；只允许一条语句。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "要执行的 SELECT 语句"},
                },
                "required": ["sql"],
            },
        },
    },
]


# ========== 实际执行函数（模型看不到这里） ==========

def _search_knowledge(query: str, top_k: int = 3) -> dict:
    """知识类工具：复用 Day 6 的完整 RAG（检索 + 生成 + 出处）"""
    result = rag_service.answer(query, k=top_k)
    return {"answer": result["answer"], "sources": result["sources"]}


def _json_safe(value):
    """把 SQL 查出来的值转成 JSON 能序列化的类型

    MySQL 的 DECIMAL 返回 Decimal、DATETIME 返回 datetime，
    json.dumps 都不认识，必须转成 float / ISO 字符串。
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _query_data(db: Session, sql: str) -> dict:
    """数据类工具：执行模型生成的 SELECT，返回结果（NL2SQL，Day 8）

    安全三件事：
      1. 只允许 SELECT（防止模型把表删了/改了）
      2. 只允许单条语句（去掉结尾分号后，再出现分号 = 多条，拒绝）
      3. 最多返回 20 行（防止把整张表倒进上下文，token 爆炸）
    """
    cleaned = sql.strip()
    # 去掉结尾分号后，再出现分号就是多条语句
    body = cleaned.rstrip(";").strip()
    if not body.lower().startswith("select"):
        return {"error": "只允许 SELECT 查询"}
    if ";" in body:
        return {"error": "只允许单条 SQL 语句"}

    try:
        result = db.execute(text(body))
        if not result.returns_rows:
            return {"error": "这不是一条查询语句"}
        rows = result.fetchall()
        columns = list(result.keys())
        # 每个值过一遍 _json_safe，避免 Decimal/datetime 撑爆 json.dumps
        data = [
            {k: _json_safe(v) for k, v in zip(columns, r)}
            for r in rows
        ]
        return {
            "columns": columns,
            "rows": data[:20],  # 截断，最多 20 行
            "总行数": len(rows),  # 告诉模型实际有多少行（可能被截断）
        }
    except Exception as e:
        # 错误回传给模型，让它自己重写 SQL（错误自愈）
        return {"error": f"SQL 执行失败：{e}"}


# ========== 执行器：按名字找到函数并调用 ==========

def run_tool(name: str, arguments: dict, db: Session) -> dict:
    """按工具名分发到具体函数，返回结果（给 Agent 循环用）"""
    if name == "search_knowledge":
        return _search_knowledge(**arguments)
    if name == "query_data":
        return _query_data(db=db, **arguments)
    return {"error": f"未知工具：{name}"}
