"""工具说明书边界测试（Day 25.1：真实文档暴露的工具选错）

背景：用户上传上市公司年报问"流动负债"数据，Agent 误判成"数据库数据"
去调 query_data（查 orders 表），结果查到"知识库中没有"。根因不是代码，
是工具 description 没划清边界——模型只看说明书选工具。
修法：search_knowledge 明确覆盖"文档里的具体事实/数据"，
query_data 明确"只能查系统数据库业务表，文档数据请走 search_knowledge"。
"""

from app.agent.tools import TOOLS


def _tool_desc(name: str) -> str:
    """按工具名取 description（模型只能看到这份说明书）"""
    return [t for t in TOOLS if t["function"]["name"] == name][0]["function"]["description"]


def test_search_knowledge_covers_document_data():
    """知识工具要覆盖"文档里的数据"——年报财务数字不该漏出触发范围"""
    desc = _tool_desc("search_knowledge")
    assert "具体事实和数据" in desc
    assert "年报" in desc


def test_query_data_limited_to_db_tables():
    """数据工具明确"只查数据库业务表"，不能拿去查文档数据"""
    desc = _tool_desc("query_data")
    assert "系统数据库中的业务表" in desc
    assert "search_knowledge" in desc


def test_query_data_still_says_orders():
    """数据工具的靶子仍是 orders 表（权限/描述旧断言不破）"""
    desc = _tool_desc("query_data")
    assert "orders" in desc
