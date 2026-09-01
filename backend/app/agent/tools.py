"""Agent 的工具：给模型的"说明书"（TOOLS）+ 实际执行函数

关键认知：模型看不见下面的 Python 代码，它只看得见 TOOLS 这份 JSON 说明书。
description 写得好不好，直接决定模型能不能选对工具。
"""

import copy
import re
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
                # Day 19：扩容触发条件——原来只写"制度/流程/规定/政策"，
                # 用户问"工具调用方式"这类教程/课程问题，模型判断不是知识类就不查库。
                "当用户询问公司制度、流程、规定、政策、概念、教程、课程内容等知识类问题时使用。"
                # Day 25.1：真实文档暴露的工具边界——问年报"流动负债"时模型误判成
                # "数据库数据"去调 query_data。这里明确：文档里的具体事实/数字
                # 也走知识库检索，因为它们在文档里，不在系统数据库里。
                "用户上传的文档里的具体事实和数据也走本工具，"
                "如年报的财务数字、报表数据、统计数字、产品参数等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "用户的问题或想检索的内容"},
                    # Day 22：教模型按问题类型选 top_k——列举/概括类问题召回要够全
                    # Day 25.x：别再教模型用 3——单点事实的答案片段常排 top-3 之外，
                    #          用 3 会把答案漏出上下文。两类都给 8~10，别用 1~3 这种过小值。
                    "top_k": {
                        "type": "integer",
                        "description": (
                            "返回的最相关片段数，默认为一个足够大的值。别用 1~3 这种过小的值，"
                            "答案片段有时排在较后位置，容易漏掉正确答案。"
                            "列举/概括类问题（如\"有哪些工具\"\"列出所有流程\"）"
                            "建议 8~10；找具体数值、日期、人名等具体事实类问题"
                            "（如\"报销限额是多少\"）也建议 8~10，确保答案被召回再回答。"
                        ),
                    },
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
                # Day 25.1：工具边界——query_data 只能查系统数据库的业务表。
                # 用户上传的知识库文档（如年报、制度）里的数据不在数据库里，
                # 别用本工具，否则查到"知识库中没有"就错了。
                "注意：本工具只能查询系统数据库中的业务表（orders）。"
                "用户上传的知识库文档（如年报、制度）里的数据不在数据库里，"
                "不要用本工具，请改用 search_knowledge。\n"
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

# 列举/概括类关键词：命中说明问题要"召回全面"，给大 top_k（Day 22）
# 对应两个真实故障：问工具列表只答 3/17 个、图描述 chunk 被挤出前 3
ENUM_KEYWORDS = (
    "有哪些", "哪些", "列出", "列举", "所有", "全部", "清单",
    "几个", "几种", "分别", "对比", "总结", "概括", "概述", "汇总",
)


def _infer_top_k(query: str) -> int:
    """按问题类型推断检索量：列举/概括类、以及单点事实类都要召回够全

    Day 22：search_knowledge 固定 top_k=3 的根因不是管道不通——
    top_k 参数本来就能从模型一路传到 Chroma 的 n_results，
    而是没人决定 k 该取多大，模型几乎从不传这个可选参数。
    这里做后端兜底：模型没给 top_k 时，按问题里的关键词判断类型。

    Day 25.x：把"具体事实类"从 3 提到 8（推翻 Day 22 的"事实类精确优先"）。
    理由：用单文档基准实测（20 问答对，按答案是否进上下文判命中），
    数值/日期/人名这类单点事实的答案片段常排在 top-3 之外（实测第 4~6 位）。
    默认 3 会把这些答案直接漏出模型上下文——模型只能瞎编或说"资料没有"。
    宁可在上下文里多塞几段（Day 24.5 的相关性过滤会滤掉远的，LLM 也会甄别），
    也别让该有的答案漏掉。代价是 hit@3（前三命中率）不变，涨的是召回率。
    """
    return 10 if any(kw in query for kw in ENUM_KEYWORDS) else 8


def _search_knowledge(query: str, top_k: int | None = None) -> dict:
    """知识类工具：复用 Day 6 的完整 RAG（检索 + 生成 + 出处）

    默认值 None 而不是 3（Day 22）：这样才能区分"模型没传"（→ 推断）
    和"模型特意传了 3"（具体事实类问题，精确优先，尊重它）。
    最后 clamp 1~10——Agent 链路是唯一没夹紧 top_k 的地方，模型可能传 100000。
    """
    if top_k is None or top_k <= 0:
        top_k = _infer_top_k(query)
    top_k = min(max(top_k, 1), 10)
    result = rag_service.answer(query, k=top_k)
    return {"answer": result["answer"], "sources": result["sources"]}


# ========== Day 25.3：模型不调工具的强制检索兜底 ==========
# 背景：模型"经常"违反规则 1 不调 search_knowledge 就直接答，甚至编数字还假称
# "根据企业知识库"。提示词规则是软的，代码兜底才是硬的——模型不肯检索，
# 后端替它检索，把结果注入 context 逼它基于资料重答。
# 排除的系统元问题（规则 2 允许不检索直接答，兜底别误伤）：
META_QUERY_KEYWORDS = (
    "你这个", "你的工具", "你的系统", "平台架构", "技术栈",
    "怎么用工具", "你的功能", "你是谁", "你支持", "你叫什么",
)


def _is_meta_query(query: str) -> bool:
    """这是"关于系统本身"的元问题吗？（是则不强制检索）"""
    return any(kw in query for kw in META_QUERY_KEYWORDS)


def _force_retrieve(query: str) -> str:
    """强制检索知识库，返回可直接注入 context 的参考资料文本（兜底用）

    不调 LLM、不生成答案——只把最相关的 chunk 原文拼出来。
    无结果时明说"没有"，让模型无从编造。
    """
    chunks = rag_service.retrieval.search(query, k=3)
    chunks = rag_service._filter_relevant(chunks)
    if not chunks:
        return "（知识库中没有相关文档）"
    return "\n\n".join(
        f"[资料{idx + 1} 来源:{c['source']}]\n{c['text']}"
        for idx, c in enumerate(chunks)
    )


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


def _validate_query_scope(sql: str) -> str | None:
    """限制数据工具只能读取 orders，避免 SELECT 变成任意表读取器。"""
    lower = sql.lower()
    if re.search(r"--|/\*|\*/|#", sql):
        return "SQL 不允许包含注释"
    if re.search(r"\b(?:union|with|into|outfile|load_file)\b", lower):
        return "SQL 包含不允许的查询结构"
    if len(re.findall(r"\bselect\b", lower)) != 1:
        return "只允许查询 orders 表且不允许子查询"
    if re.search(r"\bfrom\b[^;]*(?:,|\bjoin\b)", lower):
        return "只允许查询 orders 表，不允许 JOIN 或多表查询"

    tables = re.findall(r"\bfrom\s+([`a-zA-Z_][\w$]*(?:\.[`a-zA-Z_][\w$]*)?)", lower)
    if len(tables) != 1 or tables[0].strip("`") != "orders":
        return "只允许查询 orders 表"
    return None


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

    scope_error = _validate_query_scope(body)
    if scope_error:
        return {"error": scope_error}

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
