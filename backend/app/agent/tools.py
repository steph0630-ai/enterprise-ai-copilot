"""Agent 的工具：给模型的"说明书"（TOOLS）+ 实际执行函数

关键认知：模型看不见下面的 Python 代码，它只看得见 TOOLS 这份 JSON 说明书。
description 写得好不好，直接决定模型能不能选对工具。
"""

import copy
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import ADMIN_ROLES  # 管理端角色集合（单一来源，别再漏放行）
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


def build_tools(user=None) -> list[dict]:
    """给模型的工具说明书：非管理员时，把"只能查本部门"写进 query_data 描述（Day 12）

    模型看不见代码，只看 description。要让模型遵守部门权限，
    就得在说明书写清楚当前用户属于哪个部门、SQL 必须带上部门条件。
    """
    tools = copy.deepcopy(TOOLS)  # 每次复制一份，别污染全局的 TOOLS
    # 管理端（admin / super_admin）不受部门限制，不写权限描述
    # （Day 17 修：原来只认 admin，super_admin 被当成普通员工）
    if user and user.role not in ADMIN_ROLES and user.department:
        for t in tools:
            if t["function"]["name"] == "query_data":
                t["function"]["description"] += (
                    f"\n权限：当前用户属于「{user.department}」，只能查询本部门的数据，"
                    f"生成的 SQL 必须包含 department='{user.department}' 条件。"
                )
    return tools


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


def _query_data(db: Session, sql: str, user=None) -> dict:
    """数据类工具：执行模型生成的 SELECT，返回结果（NL2SQL，Day 8）

    安全防线（Day 8 三件事 + Day 12 部门权限）：
      1. 只允许 SELECT（防止模型把表删了/改了）
      2. 只允许单条语句（去掉结尾分号后，再出现分号 = 多条，拒绝）
      3. 最多返回 20 行（防止把整张表倒进上下文，token 爆炸）
      4. 部门权限（非管理员）：SQL 必须包含本部门条件，否则拒绝
         —— 拒绝后错误会回传给模型，它自己改写 SQL 再试（错误自愈）
    """
    cleaned = sql.strip()
    # 去掉结尾分号后，再出现分号就是多条语句
    body = cleaned.rstrip(";").strip()
    if not body.lower().startswith("select"):
        return {"error": "只允许 SELECT 查询"}
    if ";" in body:
        return {"error": "只允许单条 SQL 语句"}

    # 部门权限：非管理端必须查自己部门。生产上用只读账号 + 数据库视图/RLS，
    # 这里用"SQL 里必须有本部门字样"做第 4 道防线，简单且能演示错误自愈。
    # Day 17 修：管理端（admin/super_admin）跳过，否则 E001 会被告知"只能查部门(None)"
    if user and user.role not in ADMIN_ROLES:
        if not (user.department and user.department in body):
            return {
                "error": (
                    f"权限不足：你只能查询本部门（{user.department}）的数据，"
                    f"请改写 SQL，加上 department='{user.department}' 的 WHERE 条件"
                )
            }

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

def run_tool(name: str, arguments: dict, db: Session, user=None) -> dict:
    """按工具名分发到具体函数，返回结果（给 Agent 循环用）

    user 是当前登录用户（Day 12）：query_data 靠它做部门权限校验。
    """
    if name == "search_knowledge":
        return _search_knowledge(**arguments)
    if name == "query_data":
        return _query_data(db=db, user=user, **arguments)
    return {"error": f"未知工具：{name}"}
